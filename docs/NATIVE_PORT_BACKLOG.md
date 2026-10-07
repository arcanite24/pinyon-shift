# Native port backlog

Support policy, 2026-10-05: Vulkan is the sole supported graphics API.
Direct3D 12 is legacy and unsupported; its measurements below are historical.
New runtime qualification targets Vulkan, with no automatic Direct3D 12 fallback.

Status: **open; created 2026-09-28** at `dev` checkpoint `02ceca9` (ShiftGlue
`aff6202`). This is the working plan that follows the closed
[Xenos retirement backlog](native-renderer/XENOS_RETIREMENT_BACKLOG.md). It
replaces the unordered roadmap list in the README as the source of truth for
what comes next. Assessment evidence for every claim below was gathered on
2026-09-28 from the current tree; file references use repository-relative
paths, with `sdk/` standing for `thirdparty/shiftglue-sdk/`. Raw research
notes are kept locally under `.local/backlog-research/` and are not
distributed.

## Goal

Make Pinyon Shift feel like a native PC release of *Forza Horizon*, not a
renderer preview: every setting in the game, any display, correct behaviour at
any frame rate, a real profile and achievements, a mod host, a trainer for
playthroughs, and a renderer and CPU path that use a modern machine instead of
emulating a 2012 console. Ports to Linux, macOS and Android follow on the same
architecture.

"Native PC game" is done when all of the following hold:

1. **No launcher after install.** Every player setting is changed from the
   pause menu, applies without a restart where the engine allows it, and is
   labelled "restart required" where it does not. The launcher installs,
   verifies, builds and reports crashes.
2. **No ImGui for players.** Every player-facing surface (settings, profile,
   achievements, system dialogs, toasts, trainer) is drawn by a host UI layer
   styled from the game's own fonts, textures and layout. ImGui remains for
   developer overlays only (F3, F4, console).
3. **Any display.** Any window size and aspect ratio, borderless fullscreen on
   any monitor, integer internal scales up to 4x with a quality downscale,
   Hor+ ultrawide with a correct FOV and anchored HUD, frame caps and VRR.
4. **Correct at any frame rate.** Unlocked frame rate stays the default and
   no animation, NPC, UI transition or audio path runs at the wrong speed.
5. **Fast.** The race window is GPU-bound rather than CPU-bound on the
   baseline machine, guest threads are placed and prioritised on modern CPUs,
   and no core is burned spinning.
6. **Native profile.** A chosen gamertag and picture, achievements shown and
   unlocked in-game, language selectable from the disc's 18 languages, saves
   backed up and restorable in-game.
7. **Mods and cheats.** A versioned plugin ABI, an asset overlay, data patches
   and a UI extension API, with documentation and sample mods; a trainer that
   never touches an unmodded save.
8. **Portable.** The same executor core drives D3D12 and Vulkan; Linux and
   Steam Deck ship first, macOS through MoltenVK second, Android third.

## How this backlog is organised

- **Vertical slices.** Each slice `NP-n` ends with something a player or
  modder can use, and cuts through guest hooks, SDK, host UI, config, tools,
  tests and docs as needed. Items inside a slice are `NP-n.m`.
- **Sizes** are for one engineer: S ≤ 1 week, M 1–3 weeks, L 1–2 months,
  XL > 2 months. Sizes are estimates from the code, not commitments.
- **Gates** reuse the validation rules in
  [development findings](DEVELOPMENT.md#validation-and-evidence): same seed,
  route and settings for control and candidate, three runs per arm, golden
  frame replays (`tools/test-fh1-frame-replays.py`), the affected render-test
  routes, pose-drift and simulation-time gates, and save payload hash equality
  where guest timing or numerics change. Never touch the AppData save; use
  seeds from `tools/create-render-seed.py` ([AGENTS.md](../AGENTS.md)).
- **Portability guardrails apply from NP-1 on.** New host code uses the SDK
  platform layer (no `Windows.h` outside diagnostics), fixed-function shaders
  are authored in HLSL and compiled to both DXBC and SPIR-V, and the shader
  pack format becomes backend-neutral in NP-9 before the Vulkan executor in
  NP-12 needs it.
- **Release trains.** NP-0 to NP-3 target `0.3.0`; NP-4 to NP-8 target
  `0.4.0`; NP-9 to NP-11 target `1.0` (Windows complete); NP-12 to NP-14 are
  the `1.x` platform releases. Trains can be re-cut; the dependency graph in
  the slice map is what matters.

## Where the code stands

| Area | Finding | Evidence |
| --- | --- | --- |
| Renderer identity | What shipped is the Xenia D3D12 backend with a native surface owner. The EDRAM render-target cache and runtime shader translation are gone, but per-draw register-to-pipeline derivation, Xenia's constant-buffer and root-signature model, the tiled guest-memory texture cache and a runtime DXBC geometry-shader emitter are still on the hot path. The native executor replaces one component (surfaces, tiles, clears, resolves) inside `IssueDraw`. | `sdk/src/graphics/d3d12/command_processor.cpp:2303-2846`, `sdk/src/graphics/d3d12/pipeline_cache.cpp:1695-1916, 2578-3622`, `sdk/src/graphics/d3d12/texture_cache.cpp:1662-2151` |
| Dead code | The Vulkan backend, SPIR-V translator, EDRAM cache and PM4 disassembler (about 40k lines) are not compiled on Windows. Two shader-hash allowlists remain on the hot path. Modern ZPD paths, dead readback cvars and SNR-M02 trace cvars are compiled but idle. 73 of 174 tool scripts belong to retired scene-native research and 40 of them require a log authority no build can produce. | `sdk/src/graphics/CMakeLists.txt:45-101`, `command_processor.cpp:2360-2372, 2480-2495`, `command_processor.cpp:41-95, 254-396` |
| Renderer performance | Race window: 24.95 ms median frame, 12.61 ms GPU span, so the frame is CPU-bound on the single GPU Commands thread. The whole-frame deferred tape is replayed serially at swap, `OMSetRenderTargets` is recorded per draw, fetch constants re-upload on any write, and every resolve writes the guest tiled layout into the memory mirror and is untiled again on the next fetch (15.3 M of 53 M fetches are resolve-sourced, front buffer included). Depth transfers take 9 passes because stencil is almost never proven zero. | [baselines](native-renderer/NATIVE_PERFORMANCE_BASELINES.md), `command_processor.cpp:3281`, `fh1_native_executor.cpp:1816, 1901-1966, 1053-1082`, `command_processor.cpp:1778-1780, 3845-3856` |
| CPU and threading | Guest threads are 1:1 host threads; priorities and affinities are ignored by default and nothing is pinned. The title spends two thirds of its time busy-polling a word the GPU thread writes. Texture write-watches cost a syscall plus a TLB shootdown per 4 KiB page. Every event or wait takes one process-wide recursive mutex. The build is pinned to SSE4.1, so 11,725 fused multiply-add sites call a library function. The timer queue spin-waits on a core. | `sdk/src/system/xthread.cpp:42-46, 1025-1073`, `sdk/src/system/xmemory.cpp:2112-2293`, `sdk/src/system/xobject.cpp:370-449`, `cmake/PinyonShiftRexGlue.cmake:56-66`, `sdk/src/core/timer_queue.cpp:145-147` |
| Frame rate | Unlocked frame rate is the shipped default: guest vblank runs at twice the detected refresh, gameplay integrates a variable delta observed at `0x823EDB84`, and the source-60 and HFR routes gate distinct presents and simulation time. Accelerated NPC and title animations remain an open regression with no address located. | `sdk/src/graphics/graphics_system.cpp:170-227`, `src/pinyon_shift_app.cpp:57-86`, [release notes](releases/0.1.2-preview.3.md) |
| Display | The guest still renders 1280×720 times an integer scale of 1–3 because the DXBC translator bakes the scale into shader immediates and each pack is keyed by scale. Output is letterboxed to the guest video-mode aspect; a 21:9 guest mode would stretch. No projection, FOV, safe-area or back-buffer hook exists. Borderless fullscreen only, no exclusive mode, no HDR, presenter downscale is bilinear (FidelityFX is off by default). | `fh1_native_executor.cpp:407-413, 1952`, `sdk/src/graphics/pipeline/shader/dxbc_translator.cpp:664-747`, `sdk/src/ui/presenter.cpp:874-1010`, `sdk/CMakeLists.txt:23` |
| Player-facing UI | Everything the player sees from the host is ImGui with a 10 px debug font and a green theme: XAM message box, virtual keyboard, disc error, achievement toast, F7 list. Achievements, gamercard, friends, marketplace and sign-in system screens are stubs. The gamertag is fixed to "User", `XGetLanguage` is hard-coded English, button prompts are always Xbox glyphs, and no controller remapping exists. | `sdk/src/ui/imgui_drawer.cpp:30-87`, `sdk/src/kernel/xam/xam_ui.cpp:211-663`, `sdk/src/system/xam/user_profile.cpp:28-29`, `sdk/src/kernel/xam/xam_info.cpp:185-198` |
| Game UI and assets | The game's UI is Anark Gameface (`AnarkBGF` scenes under `Scenes/ui4` in `media/UI.zip`, with Lua scripts) plus LSB2 string tables. Same-length label rewrite and row hiding are proven; adding a row is blocked at scaler-binding registration. Archives are PKZIP with Xbox LZX entries and stored entries; only a decompressor exists. Car, upgrade, wristband, event and time-of-day data is a plain SQLite database, `media/db/gamedb.slt`. | [UI API plan](UI_API_PLAN.md), `tools/fh1-ui-scene-insert.py`, `tools/fh1_archive_extract.cpp:16-57`, `.local/game/base/media/db/gamedb.slt` |
| Modding foundations | About 90 mid-asm hooks in `config/rexglue/analysis/*.toml` are the interception surface; there are no whole-function overrides and no plugin loader. Runtime DLLs can only replace indirect calls through the dispatch table. The VFS has no overlay device, but the host can swap the game mount before launch. Saves are raw files under a fixed profile identity; the plaintext save body is visible at `0x82C666D0` before encryption and is already edited there. | `sdk/include/rex/hook.h`, `sdk/include/rex/system/function_dispatcher.h:85-113`, `sdk/src/system/runtime.cpp:294-375`, `src/pinyon_shift_runtime_hooks.cpp:492-530` |
| Portability | The SDK already has Linux, macOS and ARM64 platform layers, SDL3 window/input/audio, a pinned MoltenVK stack and simde-based NEON for the PPC headers; the generated code is Clang-dialect with zero SEH scopes. The host project is Windows-only by construction (WPF launcher, PowerShell tools, `Windows.h` in diagnostics and app, D3D12-only executor, shader pack and texture-cache additions). The Vulkan backend has drifted about 25 base-class commits and its compile state is unverified. | `sdk/CMakePresets.json`, `sdk/src/core/CMakeLists.txt`, `src/pinyon_shift_diagnostics.cpp:3-5`, `sdk/src/graphics/vulkan/` |
| Distribution | Releases ship only independently authored source and the launcher; the user builds the executable and shader packs from their own disc. First build is 20–60 minutes and about 25 GB. CI checks the boundary, Python tools and the launcher; it never compiles C++ and the four C++ test targets are excluded from the default build. | [legal](LEGAL.md), `.github/workflows/ci.yml`, `CMakeLists.txt:47-79` |

## Slice map

| ID | Slice | Player- or modder-visible outcome | Size | Depends on | Train |
| --- | --- | --- | --- | --- | --- |
| NP-0 | Clean native baseline | Smaller renderer DLL, no allowlists, one occlusion path, car-selection textures fixed, stale tools gone, graphics prepared only when graphics code changes | M | — | 0.3.0 |
| NP-1 | In-game settings and host UI layer | "SETTINGS" in the pause menu opens a native-looking screen; hot settings apply instantly | L | NP-0 | 0.3.0 |
| NP-2 | Fast frame, pass 1 | Measurably shorter race frames from the renderer's CPU path | M | NP-0 | 0.3.0 |
| NP-3 | Modern CPU, pass 1 | Threads placed and prioritised, no spinning cores, NPC and UI animations at real time | M–L | NP-2.0 | 0.3.0 |
| NP-4 | Any display | Any window size, 4x scale, sharp downscale, Hor+ ultrawide with FOV slider, frame caps and VRR | M–L | NP-1 | 0.4.0 |
| NP-5 | Native profile, achievements, dialogs, language | Gamertag and picture, in-game achievements, styled system dialogs, 18 languages, save backups, photo export | M | NP-1 | 0.4.0 |
| NP-6 | Input | Controller remapping, keyboard prompt text, haptics options | S–M | NP-1 | 0.4.0 |
| NP-7 | Mod host v1 | Plugin ABI, hook points, symbol table, asset overlay, isolated modded profile, docs and samples | M–L | NP-1 | 0.4.0 |
| NP-8 | Cheat menu v1 | Trainer screen: time scale, teleport, career skip, save editor, world toggles | M | NP-7.1, NP-7.5 | 0.4.0 |
| NP-9 | Fast frame, pass 2 | GPU-bound race window; executor core split; backend-neutral pack | L | NP-2, NP-3 | 1.0 |
| NP-10 | Content mods | Per-asset overrides, database patches, texture replacement, optional Lua | M–L | NP-7 | 1.0 |
| NP-11 | UI extension API, production | Extensions add and drive menu items and HUD widgets through the stable API | M (+L research) | NP-1, NP-7 | 1.0 |
| NP-12 | Linux and Steam Deck | Native Linux build with the Vulkan executor and Deck qualification | XL | NP-9 | 1.x |
| NP-13 | macOS | Apple Silicon build through MoltenVK | L | NP-12 | 1.x |
| NP-14 | Android | ARM64 Vulkan build with a cross-build workflow | XL | NP-13 | 1.x |
| NP-15 | Vulkan support | Vulkan is the sole supported graphics API; qualify performance, preparation and hardware support | L | NP-12.4 | 1.x |
| NP-X | Quality and tooling | C++ tests and SDK build in CI, pruned tools, hardware qualification | ongoing | — | all |
| NP-D | Distribution and first run | Faster first build, launcher core reusable across platforms, signing | ongoing | — | all |

## Working order

**Renderer direction (updated 2026-10-05): Vulkan only (NP-15).** Vulkan is
the supported graphics API on Windows and every planned platform (Linux and
the Deck, macOS through MoltenVK, Android). Direct3D 12 is legacy and
unsupported. New renderer work and qualification target Vulkan, including
NP-15's performance, preparation and hardware items and the Linux build
(NP-12.1, 12.2, 12.7).

**Performance direction (set 2026-09-30): 4K at 120 fps on Vulkan.** The
maintainer's target is the race at 3x (3840x2160) at a steady 120 fps on
the baseline machine, on Vulkan. The measured state (D3D12 1x CPU-bound at
18 ms, Vulkan 3x GPU-bound at 29 ms) and the plan to get there are in the
[performance backlog](PERFORMANCE_BACKLOG.md) (PB-0 to PB-5), which
supersedes NP-2's deferred items, NP-3.8, NP-9.1 to NP-9.5 and NP-15.1
and revives them with the sizes they earn at 3x and 120 Hz. Aggressive
optimizations and results that are not 100 % faithful are accepted for
that target under its gates.

**Current goal (set 2026-09-28): finish NP-0, then NP-1.** NP-0 shrinks the
code every later slice touches, and NP-1 is both the largest remaining
"feels native" change and the surface NP-4 to NP-8 build on. Order:

1. **NP-0.8** first: every rebuild and every new pack miss costs about ten
   minutes of graphics preparation today, and NP-1 alone means dozens of
   rebuilds.
2. **NP-0.2** to **NP-0.5**, then the NP-0.6 repair of cards saved by older
   builds (its cause is already fixed).
3. **NP-1.1** to **NP-1.7**.
4. Between NP-1 items, the small measurable NP-2 items: **NP-2.1**,
   **NP-2.2** and **NP-2.8**, then NP-2.3 to NP-2.5.
5. Then NP-3, whose thread-placement and busy-poll work matters more now
   that the GPU commands thread has less to do.

NP-0.7 moved to NP-9.4, which bumps the pack format anyway.

Status on 2026-09-29: NP-0.1 to NP-0.5 and NP-0.8 are done, and NP-1 is
done, gate runs included. NP-0.6's repair of cards saved by older
builds waits on a product decision, because it would change player save files.
NP-2.1, NP-2.2 and NP-2.8 are done; NP-2.3 to NP-2.5 were measured and not
built (NP-2.4 waits for AMD or Intel hardware). NP-3.2, NP-3.4 and NP-3.6 are
done, NP-3.1 is built and off by default, NP-3.0 and NP-3.3 are done in part.
NP-4.1, NP-4.2 and NP-4.6, NP-5.1 to NP-5.6 and NP-6.1, NP-6.2 and NP-6.4
are done. See [Needs a person](#needs-a-person) for what waits on hardware or
a decision.
Open from the 2026-09-29 play test: NP-2.9 (cinematic artifacts) and the
car-purchase case of NP-3.7; NP-1.8 (settings screen slowdown) is fixed.

## Needs a person

Work the autonomous passes cannot finish, with what each needs. Everything
else in a row marked done was checked by scripted routes, replays or A/B
runs on the development machine (Ryzen 7 5800X, RTX 4080).

| Item | What is left | Needs |
| --- | --- | --- |
| NP-2.4 | The one-pass `SV_StencilRef` depth transfer (patch in `.local/np24/`) | An AMD or Intel GPU to qualify it |
| NP-2.9 | Whether the in-game blue-wristband cinematic still shows green and pink, and whether the title update or another disc ships `WristbandGet.wmv` (absent from the supported retail disc) | A play-through to the next wristband (or a save at the festival hub with COLLECT BLUE WRISTBAND pending, which the render seed is not placed for), and the title update's file list |
| NP-3.1 | Latency-critical thread placement on P-cores and E-cores | A hybrid Intel CPU |
| NP-3.7 | Which animation plays too fast after buying a car before a race at the unlocked rate (the race crowd running fast, reported 2026-09-30, is reproducible by route and tracked in NP-3.7 itself) | A short clip or the moment it happens, from the player who saw it |
| NP-4.5 | That VARIABLE REFRESH RATE runs the display at the game's rate without tearing artifacts | A VRR (G-SYNC or FreeSync) display |
| NP-6.3 | DualSense and Steam Input through SDL, a Deck controls layout | Those controllers and a Steam Deck |
| NP-12.1, 12.2, 12.7, 12.8 | Configuring and building on Linux (the presets and POSIX sources of NP-12.1 and NP-12.2 are written but unbuilt), Linux tooling and Steam Deck qualification | A Steam Deck (the Linux toolchain is approved in WSL, 2026-09-30) |
| NP-13 | The macOS port (ARM64 baseline, MoltenVK, app bundle) | A Mac and its toolchain |
| NP-14 | The Android port (NDK build, fibers, mobile GPU, sideloading; running NP-14.3 on a 16 KiB kernel) | The Android NDK and a reference device |
| NP-X | AMD, Intel and lower-end GPU qualification; an unscripted drive before each train | Hardware and a player |
| NP-15.6 | The Vulkan renderer on an AMD and an Intel GPU, a gate for making Vulkan the default | That hardware |

## NP-0 Clean native baseline

**Why first.** The user-facing "renderer preview" caveat comes from carrying
Xenia machinery the native executor does not need, and every later slice
touches the same files. Removing what is dead, and naming what is not yet
native, shrinks the surface the performance and portability work has to
reason about. Only Xenos-emulation layers are removed here; the PM4 command
processor, register file, guest-memory mirror and the executor are the guest
GPU ABI and stay.

| Item | Work | Size |
| --- | --- | --- |
| NP-0.1 | **Done** (SDK `7ca40bf`): the translator bodies build only into the producer, `packet_disassembler` and `sampler_info` are gone, the SNR-M02 trace and the never-defined `d3d12_readback_*` declarations are removed, and the Vulkan-only readback and EDRAM-cache cvars are declared only in Vulkan builds (kept rather than deleted because non-Windows builds still compile the Vulkan backend until NP-12). The runtime DLL shrank 2,625,536 to 2,589,184 bytes; the producer rebuilt the 1x pack byte-identical. | S |
| NP-0.2 | **Done** (SDK `c0213b6`): no shader-hash literal remains on the draw path. The no-output skip now applies to any draw that tests and writes neither depth nor stencil, writes no color and exports no memory outside an occlusion query (it also catches the no-pixel-shader variant of the same point draws, so the pack loses one unused entry), and the linear video upload applies to every linear single-level unsigned 8-bit texture whose guest pitch matches the upload footprint. `fh1_scaled_32` and the reflection-cube import stay: they are keyed on texture layout, not shader identity. `check-fh1-constant-no-output.py` and `check-fh1-video-upload.py` are deleted; `check-fh1-scaled-32bpp.py` still checks the kept path. Golden replays byte-identical, `fh1-fmv` renders the movies, `fh1-race-sync` within run-to-run spread. | S–M |
| NP-0.3 | **Done** (SDK `bdc2e94`): `legacy` (a host query per ZPD begin and end, fenced at END) is the only occlusion path. The modern lifecycle (`ExecuteModernZPD`, `ZPDLifecycle`, the report and policy headers and their unit test), the `fake`, `fast` and `strict` modes, the `occlusion_query`, `zpd_end_policy` and `zpd_end_fallback` settings, the 17 `zpd_*` performance counters and `tools/qualify-zpd.ps1` are gone; about 1,240 lines left the SDK. Without host queries the fallback reports the fixed sample count at the END sentinel. Config schema 25 strips the three settings, and the launcher writes schema 25. Golden replays byte-identical; `fh1-modes-sync` and two `fh1-race-sync` runs pass with zero misses, GPU errors and executor skips, and the schema-21 seed config migrates to 25. | M |
| NP-0.4 | **Done**: `readback_resolve` stays as a developer setting (the executor's `full` mode is the reference for guest-visible resolves) that no launcher or default config writes. Migration and `set-graphics-experiment.ps1` drop it only from configs older than schema 24, which older launchers wrote for players, and keep it in current configs; [development findings](DEVELOPMENT.md) describe the modes. | S |
| NP-0.5 | **Done.** 101 research tools, 81 of their tests and three classifier configs from the retired static-world, track, vehicle, visibility, semantic, dispatch, lineage and Xenos-era census research are gone (recovery point `b59061f` in [RESEARCH.md](native-renderer/RESEARCH.md)). The GPU execution corpus, which had recorded nothing since `bccf126`, is removed with the pass tracker, the SDK `GraphicsFh1ExecutionKey` ABI, `rank-fh1-gpu-corpus.py` and the corpus parts of the render-test runner and discovery recorder; `pinyon_shift_fh1_gpu_corpus` stays as the switch for sampled native GPU timings. Found on the way: every graphics preparation since `bccf126` had written an empty startup pipeline allowlist, now built from the pipelines the preparation route creates (`b59061f`: 0 to 379 prewarmed pipelines, pipeline creations during the strict route 384 to 16). The shader capture no longer reports a Xenos fallback. | S |
| NP-0.6 | Striped car cards: the cause was found and fixed in XR-04 (SDK `0bf0658`): the cards are the profile's `Thumbnails/Thumbnail_N.xdc`, which the game renders, resolves and compresses from guest memory when it saves a car, and the renderer never copied that resolve back, so saved cards held stale memory. New cards are correct (about 34 KB); cards saved by earlier builds stay striped (275-845 KB of compressed noise) until the game saves them again. Remaining: find which game actions re-save a card (buying, painting, upgrading) and whether a missing card is re-rendered, then give players a repair: re-render stale cards through that path, or tell them which action fixes a card; any change to save files goes through a backup. [BUGS.md](../BUGS.md) is updated. **Approved 2026-09-30:** the maintainer agreed that the repair may change player save files (through a backup). **Striped cards removed at start (2026-09-30):** a card is a `cxds` header (version 2, 884,788 bytes uncompressed, then the compressed size) over a 768x288 texture; rendered cards compress to 3-4% and the striped ones to 31-63% (the maintainer's save: cards 9 and 12 rendered, 3 to 6 striped), so `pinyon_shift_repair_car_cards` (on) moves every card above 15% to `<state>/backups/car-cards/<UTC>/` before the title opens its files. Car select then shows an empty card instead of noise (captures of the seed with the repair off and on); the title opens only the cards that exist, so routes keep the seed's cards (`run-fh1-render-test.py` turns the repair off unless a test asks for it). Re-rendering the removed cards is still open: the title writes a card only when it saves a car, through a car-save task (`sub_82555C88`: car at `+76`, render flag `+84`, save flag `+85`) that calls `sub_82546460(&job, car, 1, 0)` to queue the studio render and the compressed write (`sub_82546168` builds `Thumbnails\Thumbnail_<car id at +652>`); queuing that for each car whose card was removed needs the garage's car list and the task's lifetime found first. Until then a card comes back when the title next saves that car (confirmed for purchases; the other callers, likely paint and upgrades, are still to confirm). | S–M |
| NP-0.7 | **Moved to NP-9.4**: prebuilt geometry shaders need a pack format bump, which NP-9.4 makes anyway. The runtime keeps `CreateDxbcGeometryShader` until then. | — |
| NP-0.8 | **Done** (SDK `bf7af69`). The disc corpus translates on one worker per logical processor (`--fh1_shader_production_threads`), and the per-file costs that dominated under real-time antivirus scanning are gone: the extractor writes one `corpus.blob` instead of 12,846 files, the capture appends bytecode to one `dxil.blob` instead of 24,700 files, and its manifest checkpoints at powers of two. A 1x production with recorded misses on 16 threads: corpus load 55 s to 33 ms, translation 105 s to 1.15 s, extraction 19 s to 7 s, whole preparation 6 min 36 s to 4 min 32 s, of which the two game routes are now about 4 minutes; packs byte-identical to the single-threaded producer. `tools/prepare-fh1-shaders.ps1` keys the pack and startup catalogs on the translator, shader-analysis, pipeline-description, pack and capture sources instead of the built binaries, so rebuilding host code, hooks or the renderer's command path no longer prepares graphics again. The game routes and incremental misses stay [pending](#faster-graphics-preparation). | S–M |

**Gates.** `rexgpu-fh1` compiles without translator bodies; every `REXCVAR_DECLARE` under `REX_HAS_D3D12` has a
definition; no `ucode_data_hash() == 0x…` literal under
`sdk/src/graphics/d3d12`; `tools/tests` pass; golden frame replays are
byte-identical; `fh1-race-sync`, `fh1-modes-sync` and `fh1-fmv` run with zero
pack misses and zero executor skips; `occlusion_query` has one behaviour and
the config writer and migration agree; frame-time medians within run-to-run
noise of the current baselines; car selection shows real car cards; a
rebuild that touches no graphics input launches without preparing, and the
parallel producer writes a pack byte-identical to the single-threaded one.

## NP-1 In-game settings and host UI layer

**Why second.** This is the single biggest "feels native" change and every
later slice needs an in-game surface: display settings (NP-4), profile and
dialogs (NP-5), input (NP-6), the trainer (NP-8) and mod UIs (NP-7). The
native UI4 insertion route stays blocked at scaler-binding registration
([UI API plan](UI_API_PLAN.md)), so the entry point uses the two proven guest
mutations (same-length label rewrite and an activation hook) and everything
past that row is host-drawn with the game's own assets.

| Item | Work | Size |
| --- | --- | --- |
| NP-1.1 | **Done**: `PinyonShiftApp` overrides `OnConfigureFonts` and `OnConfigureStyle` (`src/ui/host_style.cpp`): a 16-logical-pixel system font (Segoe UI on Windows, Arial on macOS, DejaVu Sans on Linux, the SDK font as fallback) rasterized at the window DPI so it stays sharp, and a charcoal, orange and magenta palette with roomier spacing for every ImGui surface, including the XAM message box, keyboard dialog, toast and F7 achievements list. The runtime log names the font and DPI scale. | S |
| NP-1.2 | **Done** ([UI assets](UI_ASSETS.md)): `tools/inspect-fh1-ui.py --decode-assets` catalogues the four UI archives, decodes all 4,373 `.xds` textures (RGBA8, BC1 to BC4 and DXT3A, untiled with the packed mip tail and swizzle) to PNG with a read-back check, byte-exact re-encoding for the 2,825 uncompressed ones, and records every vector font's metrics and glyph table plus the full `fontmap.xml`. Decision: neither bitmap fonts nor a TTF. The Latin fonts are GPU meshes (no installed TTF matches their advances within 5 %); their coverage rule was recovered from the title's shader and the host UI rasterizes the game's own fonts from the player's disc. | M |
| NP-1.3 | **Done**: `pinyon_shift::hostui::HostUi` (`src/ui/hostui/`) is a `UIDrawer` and window input listener on the SDK `ImmediateDrawer`. It reads `Fonts.zip` and `Horizon.zip` from the disc at first open (23 ms), rasterizes the vector fonts at the output size into glyph atlases, and uses the title's selection mask and button art. Layout is the title's 1280x720 space fitted into the painted guest output, which the SDK presenter now exposes (`GetPaintedGuestOutputRectFromUIThread`), so it scales with the internal resolution and keeps the 90 % safe area. Focus model with wrap-around and disabled rows; pad (d-pad, stick with repeat, A, B, Start), keyboard (arrows, numpad, Enter, Space, Escape, Backspace) and mouse (hover, click, wheel, right-click back). While open the title sees system UI (`xeXamSetHostUIActive`: `XN_SYS_UI` and `XamIsUIActive`, so it pauses into its own pause menu), and a `ReXApp` guest-input capture gives the guest untouched pads (now also for XInput) and no mouse-and-keyboard input, while `InputSystem::GetHostPadState` reads the pads for the menu under a new device lock. F6 (`bind_game_menu`) opens a SETTINGS screen with the live FULLSCREEN and MOUSE AND KEYBOARD toggles until NP-1.4 and NP-1.5 replace it. The guest-thread queue waits for NP-7.1; nothing here runs guest code. | L |
| NP-1.4 | **Done**: `src/ui/settings_menu.cpp` puts SETTINGS (F6 until NP-1.5) over the host UI with Display (fullscreen, vsync, frame-rate limit, variable refresh rate, game frame-rate limit), Graphics (resolution scale, anisotropy, anti-aliasing, motion blur, depth of field), Audio (master volume through the new `pinyon_shift_master_volume` and the SDK output gain, mute), Controls (mouse-and-keyboard mode and the key each pad control maps to) and Profile placeholders for NP-5. Live settings apply at once; the others save and show a RESTART badge that turns orange, with a note, while a saved change is not live yet (NP-1.6 makes the cheap ones live). Every change is written at once through `src/config/host_config.cpp`, with a backup in `config/backups` before the first save of a session. The launcher's edits moved into `tools/host-config.ps1` with the same rules, and `tools/tests/test_host_config.py` checks that both write identical bytes and that the launcher reads back what the game writes. No LOD-bias setting exists yet to expose. | M |
| NP-1.5 | **Done**: the offline pause menu's MULTIPLAYER row reads SETTINGS and opens the settings screen. Label: when `pausemenu.str` loads, only entry `0xDD6B` (`IDS_Multiplayer`) is rewritten, in place and only where it fits (the title reads strings up to the NUL; `IDS_MultiplayerOption` is left alone). Activation: a midasm hook on case 6 of `CPauseMenu`'s action switch (`sub_82739D00`, 0x82739DB0, vtable 0x8205109C checked) opens the screen on the UI thread and jumps to the switch's common exit (0x8273A10C), skipping the "MULTIPLAYER UNAVAILABLE" popup; the pause menu stays open with the row focused. Closing keeps the guest's input captured until the closing press is released, so B or Enter does not also resume the title. `pinyon_shift_pause_settings=false` restores the stock row. `fh1-pause.fh1test` passes three consecutive runs. | M |
| NP-1.6 | **Done**: anti-aliasing (`swap_post_effect`, through a change callback to the command processor), the game frame-rate limit (`pinyon_shift_fh1_render_fps_limit`, reread every guest-vblank tick) and variable refresh rate (the D3D12 presenter recreates its swap chain when the tearing preference changes) apply live; only the resolution scale still needs a restart. F11 (`bind_fullscreen`) toggles fullscreen and saves it. Pad input in host menus is applied after drawing, so window and swap-chain changes never happen inside a paint. `fullscreen`, `vsync`, the presentation limit, anisotropy, motion blur, depth of field, keybinds and `mnk_*` were already live. | S |
| NP-1.7 | **Done**: the launcher's graphics panel keeps only the internal resolution (a scale needs shaders prepared before launch) and an OTHER SETTINGS button that explains the rest is in game (F6). `set-graphics-experiment.ps1 -Action Apply` writes only the settings it is given, so a launcher save no longer resets in-game choices, and it no longer forces `vsync = true`; `test_graphics_settings.py` covers a scale-only save keeping them. Install, verify, build, play and report were already the launcher's flow. | S |
| NP-1.8 | **Done** (SDK `60455b0`). Cause: without vsync the guest vblank ticked at 1 kHz, and FH1 steps its simulation once per two vblanks (the play-test log shows 50-80 steps in each 110 ms frame against 1-4 normally), so turning vsync off ran 500 simulation steps a second; where a step is expensive, as on race central's paused screens, each frame spanned ever more vblanks. Host vsync now only changes presentation, and the vblank follows the render limit or twice the display refresh either way (a player who wants more sets GAME FRAME RATE LIMIT). Repro and check: `hostkey` steps in render-test routes (SDK `28635b1` `Window::InjectKey`) open SETTINGS and turn vsync off in free roam; before, 10 vblanks and 5 simulation steps per frame; after, 2.3 and 1.15, with the vblank still at 240 Hz. | S–M |

**Gates.** The settings screen opens and closes 100 times in a scripted route
with no leaked component, stale callback or save write; it is navigable with
pad only, keyboard only and mouse only; it renders inside the 90 % safe area
at 1x, 2x and 3x; a TOML written in-game reads back identically in the
launcher; `fh1-pause.fh1test` passes three consecutive runs with no access
violation; hot settings apply within one frame and restart-required ones show
the badge; the only ImGui windows a player can reach are the XAM dialogs
pending NP-5.2.

**Gate runs 2026-09-29** (`config/render-tests/fh1-settings-gate.fh1test`,
checked by `tools/check-fh1-settings-gate.py`): three consecutive passes from
the `appdata-2026-09-27` seed. Each run opens and closes SETTINGS 100 times
with F6 and Escape, reaches DISPLAY with only the keyboard, only the pad and
only the mouse (`hostkey` and `hostclick` route steps), and then resumes free
roam and drives 112 world units, so no drawer, input listener or guest input
capture leaks: 103 `hostui.open` and 103 `hostui.closed` events, no settings
file written. Every `hostui.layout` lies inside the 90 % safe area at a 4K
fullscreen output (canvas scale 3) and a 1600x900 window at 2x internal
scale (1.25); the layout follows the painted output rectangle, so the
internal scale cannot move it. The launcher read-back and the badge are
covered by `test_host_config.py` and NP-1.4 and NP-1.6, `fh1-pause` by
NP-1.5. Player-reachable ImGui is now the XAM dialogs (NP-5.2) and the F7
achievements list and toast (NP-5.3); F3, F4 and the console are developer
overlays.

## NP-2 Fast frame, pass 1

**Why now.** The race window is CPU-bound on the GPU Commands thread while
the GPU finishes in half the time. The items below are the evidence-backed,
low-risk parts of that path; the larger rewrites (resolve aliasing, direct
recording, thread parallelism) are NP-9. Instrument first: every item has a
counter or trace to prove its share before code changes.

| Item | Work | Size |
| --- | --- | --- |
| NP-2.0 | **Done.** Instrumentation: per-frame `texture_resolve_reloads` and `texture_resolve_reload_bytes` counters, `texture_reloads`/`texture_loads` phases in `--fh1_native_gpu_profile`, the back-face stencil mask in the frame census and `tools/summarize-fh1-stencil-census.py`; CPU profile captures now run on a private state copy with a staged pack. Race results are in the [performance baselines](native-renderer/NATIVE_PERFORMANCE_BASELINES.md#race-frame-cost-breakdown): the race frame is bound by the GPU commands thread (23.1 of 25.8 ms busy; the title polls for it 9.9 ms per frame); on that thread `IssueDraw` takes 11.6 ms, tape replay 3.9, type-0 register writes 3.7 and shared-memory uploads 3.7; resolve-sourced reloads are 88 per frame (64-71 MB, 0.39-0.56 ms GPU). | S |
| NP-2.1 | **Done** (SDK `6220b1b`), in `DeferredCommandList` rather than the executor so every caller benefits: a render-target bind equal to the tape's current one is not recorded, and `Reset`/`Swap` forget the binding because each tape replays into its own command list. 98 % of binds were repeats (11.98 of 12.22 million on `fh1-race-sync`). Five interleaved pairs: race-window median 20.08 ms off vs 19.70 ms on (-1.9 %); golden replays 4/4. Control: `--d3d12_elide_repeated_render_target_binds=false`. | S |
| NP-2.2 | **Done** (SDK `e999f5d`), measured first on `fh1-race-sync`. Fetch constants: 11.19 million block uploads for 12.2 million draws, and only 3 % followed writes to slots the draw's shaders do not read, so a dirty mask by used slots would save almost nothing and was not built. Float constants: 19.4 million uploads gathered 436 million registers in 136 million contiguous runs (about 22 in 7 per upload); the gather now copies whole runs, a third of the copies, with identical buffers (golden replays 4/4). The saving, about 0.1 ms per race frame by the counts, is below what the race A/B resolves. | S–M |
| NP-2.3 | **Measured, not built.** A temporary timer around the one-use descriptor request and `CreateShaderResourceView` calls for resolve and transfer sources (`fh1_native_executor.cpp` `CreateTransferSourceViews`, `ResolveToMemory`) on `fh1-race-sync`: 0.06-0.085 ms per race frame for about 110 view sets (about 0.7 us each, descriptor request included). Persistent per-surface views would still need a copy into the shader-visible ring per use, so the saving is a few hundredths of a millisecond, below what the race A/B resolves. | S |
| NP-2.4 | Cheaper depth-transfer stencil: the NP-2.0 census shows both scene depth surfaces write nonzero stencil (REPLACE with a per-object reference) in every race window, so precision tracking alone cannot skip the eight stencil-bit passes on the dominant 4x/1x ping-pong. Replace them with one pass that writes the stencil reference from the pixel shader where `PSSpecifiedStencilRefSupported` holds, keep the bit passes as the fallback, and keep the skip for sources the census proves unwritten (`fh1_native_executor.cpp:927-936, 1053-1082`); a single-pass fast path for same-layout MSAA-only depth transfers; skip transfers whose destination is cleared before use (needs a guest-order proof from a frame dump). **Measured 2026-09-28 on an RTX 4080:** NVIDIA reports `PSSpecifiedStencilRefSupported` = no, so the one-pass stencil export helps only AMD and Intel; it was built (an `SV_StencilRef` variant of `fh1_native_transfer_from_words.ps.hlsl` and a `kTransferDestDepthStencil` pipeline) but not committed, because WARP cannot replay the frame dumps (the pack is keyed to the NVIDIA device's shader modifications) and no AMD or Intel machine was available to qualify it; the patch waits for NP-X hardware qualification. Tracking the stencil bits each depth surface may hold, to run passes only for those bits, saved 3 % of the race dump's transfer tile passes: color-to-depth transfers, among the largest pairs, make all eight bits possible. Neither is worth landing without that hardware. | M |
| NP-2.5 | **Measured, not adopted.** The frame census of the golden dumps shows quad lists only in 3D scenes (about 660 draw records in `race-4500`, 580 in `free-roam-2000`, none in the title or photo dumps), rectangle lists everywhere (27-95) and 3 point lists; only quads have a switch (`force_convert_quad_lists_to_triangle_lists`), since points and rectangles would need vertex-shader expansion and new pack variants. Converting quads: `fh1-race-sync`, three interleaved pairs, race-window median 17.55 ms off vs 17.44 ms on (-0.7 %, within noise), and the race and free-roam golden replays change (58,884 and 196,547 differing words: the triangle split interpolates across a different diagonal than the geometry shader). No speed to gain, so the geometry-shader path stays. | S |
| NP-2.6 | **Done** (SDK `e18b220`), as overlap rather than direct recording: direct recording would only move the 3.7 ms of runtime and driver time into `IssueDraw` on the same thread. A submission worker now replays each tape, executes it and signals the fence; frames split into a new submission every 1024 draws when no occlusion query is open, and the swap and every direct-queue operation of the GPU commands thread wait for the worker. `fh1-race-sync`: race-window median 21.05-21.19 ms synchronous vs 19.25-20.32 ms asynchronous (-5.5 %), p95 25.6 vs 22.3-25.2 ms; 4/4 golden replays. Controls: `--d3d12_async_submission=false`, `--d3d12_submission_split_draws=N`. One of seven async runs stalled before the title menus, a boot stall an earlier synchronous run also hit; watch its rate. | M |
| NP-2.7 | **Done** (SDK `37d0f72`): per-thread single-writer perf counters instead of two locked adds per increment, a reused range list in `SharedMemory::RequestRanges`, a known-register bitmap instead of the `GetRegisterInfo` switch on every register write, and sampler parameters reused while their fetch constant, binding filters and `anisotropic_override` are unchanged. `fh1-race-sync`, three interleaved pairs: race-window medians 25.28/24.30 ms control vs 21.13/21.21 ms on undisturbed runs, with equal per-frame draw, texture and pipeline counters. | S |
| NP-2.8 | **Done** (SDK `54e96a7`, config schema 26). `SharedMemory` now counts uploads by kind (vertex, index, texture, memexport, other) with the bytes of pages already uploaded in the same frame, in the executor report. On `fh1-race-sync` a race frame uploaded about 20 MB of vertex data in 630 requests, 2.7 MB of index data and 2.5 MB of texture data, only 0.3 % of it twice in one frame: `clear_memory_page_state = true` dropped the valid bit of every CPU-uploaded page at each frame end, so every page a draw touched was copied again. Schema 26 turns it off (the Skate 3 recomp defaults it off too) and migrates older configs; over the route, vertex uploads fall from 41.6 GB to 0.42 GB and index uploads from 5.5 GB to 67 MB. Three interleaved pairs: race-window median 20.27 ms on vs 17.80 ms off (-12.2 %), p95 24.82 vs 25.26 ms. Race, photo-mode, buy-car (car-card render) and FMV routes pass with it off, with capture differences only in timing. | S |
| NP-2.9 | Green and pink artifacts in race central, only during the blue wristband collect cinematic (play test 2026-09-29, Release `d63d14f`). **Narrowed 2026-09-29, not fixed.** The story movies can be played without a save near a wristband: a local link mirror of the game files whose `PressStart.wmv` and `.def` are a story movie, run through `run-fh1-render-test.py --game-root`. FMV_02 (the VIP-lounge scene, the likely blue-wristband cinematic) plays cleanly for 50 s. FMV_04 shows about 0.8 s of solid green (0, 77, 0) over the whole output, logo included, when the movie loops, the same with `clear_memory_page_state` true or false and at a 30 fps render limit, so neither NP-2.8 nor the frame rate causes it. The per-frame census shows the title skipping its YUV draw (VS `7156CE05`/PS `31511D87` with the three 8-bit planes) for those 35 output frames while its composite pass (`20A41D46`/`5F479FC4`) still draws. Next: a frame dump of a green frame to find which surface the composite reads, whether the console would show the same (zeroed planes also convert to green there), and whether an in-game start of FMV_02 goes green before its first decoded frame; a play-through to the next wristband with a render test would confirm the in-game case. **The cinematic's movie is missing (2026-09-30).** The wristband ceremony is the script action `CTriggerWristbandUpgrade` (registered by `sub_82987978`; execute `sub_82989D10`, factory vtable `0x8208C858`), which upgrades the wristband (`sub_824CD660`) and then assigns `GAME:\Media\UI\Videos\WristbandGet.wmv` to the UI flow's movie string (`[0x832DF00C] + 32 + 3176`, through the string assign `sub_82407B20`). That file is not on the supported retail disc: its videos folder holds only `FMV_01`, `FMV_02`, `FMV_04`, `PressStart` and the splash intros, and none of the 2,400 extracted files, archives included, contains the name (only the executable does). So the green and pink are most likely the ceremony's movie quad composited with no decoded frame: YUV planes of zero convert to green and planes of 0xFF chroma to pink, as in FMV_04's loop gap. The title loop with its movie removed shows a black screen, so a missing movie is handled there. Assigning the missing path from a host task in free roam, or calling the action's execute there, shows nothing (its game-mode check leaves free roam alone), so the in-game case still needs the hub moment; if it reproduces, the fix is to treat a movie whose file is missing as already finished. | S |

**Gates.** Three-by-three control and candidate runs on `fh1-race-sync`
(last 600 frames) and `fh1-race-sustained` summarised with
`tools/summarize-performance.py --baseline`; target at least a 15 % lower
race-window median at 1x with p95 no worse; golden replays byte-identical or
within the documented tolerance; `fh1-buy-car` thumbnail still real; executor
stats show the expected drop in transfer tile-passes and descriptor requests.

## NP-3 Modern CPU, pass 1

**Why now.** The game was tuned for three in-order cores and six hardware
threads with a fixed 30 Hz cadence; the host gives it 1:1 threads, ignores
its priorities and affinities, and lets it busy-poll. The player-visible part
is NP-3.7: unlocked frame rate is the default, and some animations run fast.
Every numerics change is gated by the pose baseline and the save payload
hash, because gameplay integrates a variable delta.

| Item | Work | Size |
| --- | --- | --- |
| NP-3.0 | **Done.** Prerequisites: instruction-level attribution for generated code (extend `tools/profile-etl-export` to emit `file:line` per sample and map generated lines back to guest addresses, which unblocks every "defer until instruction-level evidence" decision); name guest threads by start address and log `ExCreateThread` parameters; add ready-time (scheduler delay) and waker analysis to `tools/summarize-cpu-hotspots.py`; add kernel-side counters (watch faults, `VirtualProtect` calls and pages, global-lock acquisitions and contentions, critical-section spins, clock-mutex contention, timer-queue wakeups); include Microsoft symbols so kernel and CRT time can be attributed. **Partly done 2026-09-29:** guest threads are named `Guest <start address>` and each creation logs its start, context, XAPI routine, stack, flags and CPU (SDK `a33518a`); contended global-lock acquisitions and write-watch triggers, protection calls and pages are counted (`4c77124`, `88213fe`); `.local/np3/thread-cpu.ps1` samples per-thread CPU by thread name during a run. **Done 2026-09-29:** `profile-etl-export` writes each project sample's source file and line, the thread that woke each wait and every wake's scheduler delay (`ready.csv`), and `--microsoft-symbols` resolves Windows, CRT and graphics runtime modules through Microsoft's symbol server (opt-in, it downloads PDBs); `tools/map-generated-lines.py` maps samples in the generated code to `sub_<address>` and guest instruction addresses (one comment per guest instruction, 4,025 of 4,025 labels in two generated files agree with the count), refusing sources whose codegen fingerprint differs from the one `capture-cpu-profile.ps1` now records; `summarize-cpu-hotspots.py` ranks guest functions and instructions, wakers and per-thread scheduler delay; the SDK counts `clock_mutex_contentions`, `timer_queue_wakeups` and `timer_queue_callbacks` (SDK `bb3fe20`). Re-exporting the 2026-09-25 race capture resolved 62,202 source lines, 913,812 ready delays and the wakers; guest attribution of a new capture needs an elevated session, as captures always do. | M |
| NP-3.1 | **Built, off by default; hybrid measurement waits for hardware** (SDK `3c50572`). `latency_critical_thread_placement` raises the main guest thread, GPU Commands and GPU VSync above normal priority and asks for the most performant CPU sets on hybrid CPUs; honoured guest affinities (`ignore_thread_affinities=false`) map each Xenon hardware thread to its own host physical core, most performant first, instead of logical processor N. `fh1-race-sync`, three interleaved pairs each: on the 8-core Ryzen 7 5800X p95 32.99 to 30.52 ms and median 28.89 to 28.61 ms (a noisy session); restricted to four physical cores (affinity 0xFF, `.local/np3/four-core.ps1`) median 16.85 to 17.12 ms and p95 21.14 to 24.88 ms. No consistent win, so it stays opt-in. Still to measure: a hybrid (P-core and E-core) machine, where the CPU set preference is the point | S |
| NP-3.2 | **Done** (SDK `96c24ce`). `sub_829F04A8` is the predicate seven D3D fence-wait loops (`sub_823E91F0` among them) call while the fence word, at `0xFFCA4000` in the 0xE0000000 physical view, has not reached their target; it ran about a billion times per `fh1-race-sync` run. The runtime now counts the command processor's CPU-visible write packets and wakes waiters (`rex::system::WaitForGpuWrite`); the midasm hook `PinyonShiftGpuFenceWait` at the predicate's entry spins 20 us and then blocks until the next write, bounded to 1 ms so the predicate's own timeout and kick logic keep running. About 100,000 waits per run, 88 % ended by the signal. Three interleaved pairs: process CPU over the route 186 to 159 CPU seconds (-15 %), race window 3.40 to 2.88 cores; race-window median 16.89 vs 16.80 ms, p95 21.38 vs 21.23 ms; `fh1-modes-sync` passes. Control: `--pinyon_shift_block_on_gpu_fence=false`. | M |
| NP-3.3 | **Done, the rest decided against** (SDK `88213fe`): releasing a watch restored protection with one `VirtualProtect` (and TLB shootdown) per 4 KiB page, up to 1,024 pages; runs of pages that end with the same access now take one call. New per-frame counters (`write_watch_triggers`, `write_watch_protect_calls`, `write_watch_protect_pages`) show about 60-70 protection calls for 830 pages per `fh1-race-sync` race frame. Golden replays 4/4. **Rest decided against, 2026-09-29:** re-arming less often and 64 KiB watch granularity would change when the renderer sees CPU writes, and the time they could save is small. The thread sampler puts `NtProtectVirtualMemory` at 0.8 % of the race's GPU commands thread (about 0.13 ms a frame), and the guest threads that take the write faults are at most 55 % busy (see NP-3.8). | M |
| NP-3.4 | **Done** (SDK `4c77124`) except the direct object pointer: the timer queue thread yield-looped with nothing queued (about 5 CPU seconds a run; Windows only queues the 1 ms `KeTimeStampBundle` tick), and is now created on first use, blocks while empty and sleeps on the high-resolution timer until the next item is due; guest clock queries are lock-free (a published linear segment of host ticks and an atomic maximum); `RtlEnterCriticalSection` reads before each compare-exchange, pauses, and stops after 1,024 tries instead of up to 65,280. `fh1-race-sync`, two clean interleaved pairs against the previous build: process CPU 155 to 146 CPU seconds, GPU VSync thread 1.4 to 0.03, timer thread 4 to 0.4, frame medians unchanged, golden replays 4/4. The global lock is contended about 1.3 million times a run (about 260 per frame, now counted); caching object pointers in the dispatch header to skip it needs a safe-reclamation design and is left for when those contentions show on the critical path | S each |
| NP-3.5 | **Done**: the generated code writes the Xenon's fused multiply-adds as `std::fma`, a CRT call on the SSE4.1 baseline and one instruction with FMA3, bit-identical either way; it contains no separate multiply-add expressions a compiler could fuse, and the new `fma` baseline also sets `-ffp-contract=off`. Two interleaved three-pair `fh1-race-sync` A/Bs: the guest main thread uses 6-7 % less CPU (25.5 to 23.8 s, 24.1 to 22.7 s) and process CPU 1-6 % less, while the race-window frame time is unchanged within noise, bound by the GPU Commands thread. Players build locally, so instead of runtime dispatch `build-preview.ps1 -CpuBaseline auto` picks `fma` when Windows reports AVX2 (every AVX2 CPU has FMA3) and records it in `build.json`; `src/cpu_baseline_guard.cpp` stops a copied FMA build on a CPU without FMA3 with a message. Verified: the automatic preview build chose `fma` and passes `fh1-race-sync` | S to test, M to ship |
| NP-3.6 | **Done** (SDK `41c37c6`). The old vblank wait barely spun (about 11 us per wait): `sleep_for` overshot its 500 us margin, so vblanks woke about 600 us late on average and up to 2 ms. `rex::thread::SleepUntil` waits on a per-thread high-resolution waitable timer set early by the spin margin (50 us) plus a running estimate of the timer's own overshoot, then spins with `YieldProcessor`; the vblank thread and the presenter pacing use it. `fh1-race-sync` at the unlocked 240 Hz vblank: lateness 43 us mean and 0.3-1.2 ms max, about 92 us of spin per wait (2 % of a core), race-window median 16.91 vs 16.93 ms; with `host_present_fps_limit=60` the present interval median is 16.92 vs 17.21 ms. Control: `--high_resolution_timer_waits=false`. | S |
| NP-3.7 | HFR correctness: locate the per-frame-stepped NPC and title-UI animation updaters (candidates: `sub_82AE8AE0`, which multiplies the video-mode refresh by a constant, and the consumers of the main-loop delta at `owner+448`), fix them with hooks that use real time, and extend `expect-simulation-time` to animation duration. Reported in the 2026-09-29 play test: buying a car before a race plays its animation too fast at the unlocked frame rate.. **Measured 2026-09-29, not fixed**: output-frame-paced captures of the purchase at a 30 fps limit and unlocked (about 112 fps; `.local/np37/`) differ at equal frame indices after a game-state sync: unlocked reaches the showroom's close beauty camera by frame 2668 while the 30 fps run still holds the standard view at 2684, and the loading screens after the purchase advance with wall time. That fits neither a purely per-frame nor a purely timed animation, so which animation the player saw run fast is the next thing to pin down. **Second report (play test 2026-09-30, D3D12, render and present limits 120 fps):** the race crowd, the spectators behind the fences, animates too fast. This one is reproducible without a person: `fh1-race-sync` and `fh1-race-sustained` pass the crowds, so captures of the same spectators at a 30 fps limit and unlocked, synchronized by game time, should show the animation phase running ahead with the frame rate; the crowd's animation update is then the first per-frame stepper to trace and hook to real time, and the fix may cover the purchase case too | M–L |
| NP-3.8 | **Superseded by [PB-3](PERFORMANCE_BACKLOG.md#pb-3-guest-cpu) (2026-09-30): the render thread's per-frame work must fit 8.33 ms at 120 fps.** Earlier decision, not now, on NP-3.0 evidence. The candidates are codegen register-locality options (`non_volatile_as_local`, `cr_as_local`, `ctr/xer_as_local`, blocked by interior-PC resume and fiber re-entry), `vmsum` and unaligned vector store lowerings, and an AVX2 baseline. All of them speed up recompiled guest code, which is not on the race's critical path. `pinyon_shift_thread_sampler` over the 42 guest threads live in the race and GPU Commands (`--thread "Guest "`, 15 s of `fh1-race-sync`) finds GPU Commands 79 % busy while it is sampled with them. The busiest guest thread (`Guest 8255AE10`) is 55 % busy and spends the rest blocked in NP-3.2's GPU fence wait. The next are 39 % (`825A6320`) and 29 % (audio, `82FB4AF8`). NP-3.5 already cut guest CPU 6-7 % without moving the race frame. Revisit when a guest thread becomes the limit, for example once the GPU commands thread is faster or on a slower CPU. | L |

**Gates.** The fixed A/B protocol (seed `appdata-2026-09-27`,
`fh1-race-sync` last 600 frames, `fh1-race-sustained` window, three runs per
arm, frozen binary hashes); `expect-simulation-time 0.95 1.08`; pose-drift
gate on `fh1-timing-straight`; `M5_TRACE save.file.write payload_hash`
equality against control; NPC and title animation duration equal to real time
at 60, 120 and 144 Hz; process CPU seconds and per-core utilisation reported
alongside frame time.

## NP-4 Any display

**Why now.** Once settings live in-game, display options are the next thing a
PC player reaches for. Integer internal scales stay: the translator bakes the
scale into shader immediates and resolves address guest memory by integer
area, so non-integer or dynamic scale is an architecture change with no
payoff over "2x plus a good downscale". Ultrawide goes Hor+ through guest
hooks, the approach the Skate 3 fork shipped, before anyone considers a wider
back buffer.

| Item | Work | Size |
| --- | --- | --- |
| NP-4.1 | **Done**: Display has MONITOR, WINDOW SIZE (default, 720p to 2160p) and ASPECT RATIO (letterbox, crop into the overscan margin, stretch) next to FULLSCREEN, all saved through the host config with the restart badge where the SDK reads them at start | S |
| NP-4.2 | **Done** (SDK `fabe814`): the CAS and FSR 1 presenter shaders ship prebuilt, but were gated on the FidelityFX SDK that only temporal FSR 2/3 needs; the gate is now always set (publicly, so every target sees one presenter layout) and Display has OUTPUT SCALING: bilinear, CAS (sharpen, resample when downscaling) and FSR 1 (EASU with RCAS). A sharpness comparison of 2x on 4K and 3x on 1440p against the pixel-exact case is still to run | S–M |
| NP-4.3 | **Done** (SDK `c18f1d6`, `1e13348`): 4x lifts the scale gates, widens the resolve scale field and its shader, and budgets the tiled resolve range; the launcher, SETTINGS, preparation, the artifact producer and the pack tool accept it. A 535 MB 4x pack prepared after three miss-recording rounds: `fh1-race-sync` passes with no misses or errors; `fh1-free-roam` and `fh1-map` run clean and fail only their timing checks at 4x | M |
| NP-4.4 | **Done**: Hor+ works in the guest, so culling agrees. The camera's field of view is data (`CameraSettings.ini` in `camera.zip`, `FollowLowCam\FOV 48.5`, vertical degrees); `sub_823EAED0` builds the culling frustum from it and an aspect that `sub_823E22C8` returns as a viewport's width / height. A hook at that function's return (`0x823E22F4`) multiplies the aspect of the 1280x720 main view by the window's aspect over 16:9 (`pinyon_shift_hor_plus`, Display > ULTRAWIDE > WIDER VIEW, which also stretches the presentation), so the title renders and culls a wider horizontal field of view into its 16:9 image; render-to-texture views keep theirs. Verified in a 2560x1080 window: scale 1.3333, a wider free roam with everything composed, and `fh1-buy-car` passes with its thumbnail. The HUD (SDK `018f27e`): a one-frame draw log (`fh1_draw_log_frame`) showed FH1 draws it last, into the front buffer through its `2_10_10_10_AS_10_10_10_10` view after the tonemap writes it as `2_10_10_10`, with the viewport transform on (the earlier squeeze had targeted screen-space draws); `fh1_hud_squeeze`, set to the Hor+ scale, divides the NDC x of those draws, so the stretched image shows the HUD in its proportions within the central 16:9 (D3D12 and Vulkan). Checked at 2560x1080 (1.3333) and 3840x1080 (32:9, 2.0) in free roam; golden replays unchanged. A field of view setting came with it: `sub_8284EF90` returns a camera's vertical field of view (`[r3+304]`, radians) to the frustum and projection code, and a hook at its return scales it (Display > FIELD OF VIEW, 90 to 130 %, live; every camera). Host-side attempts (scaling the camera matrices as the GPU receives them) were abandoned: some transforms escape them and culling disagrees | M–L |
| NP-4.5 | **Done** except VRR, which needs a VRR display: Display has VSYNC, FRAME RATE LIMIT (`host_present_fps_limit`) and VARIABLE REFRESH RATE (tearing), Graphics has GAME FRAME RATE LIMIT (`pinyon_shift_fh1_render_fps_limit`). `fh1-free-roam`, median over the route: game limit 30, 60 and 120 give 30.1, 59.4 and 117.5 fps with no duplicate presentations and a simulation-to-wall ratio of 1.01; the host limit at 60 gives 60.0 fps. Loading and the heaviest frames stay below the higher caps | S |
| NP-4.6 | **Done** (SDK `270243b`): `force_trilinear_filtering` (live, part of the sampler reuse key) blends mips for textures the title samples linearly with point mip selection, and `texture_mip_lod_bias` (restart; samplers are cached) offsets every texture's mip level; Graphics exposes both. Anisotropy cannot go past 16x: that is the D3D12 maximum | S |
| NP-4.7 | **Done** (SDK `8e635da`, `548f9dc`): SETTINGS > GRAPHICS > RESOLUTION SCALE applies in game on D3D12. Between frames the command processor waits for the GPU. It then rebuilds the texture cache, the native executor (surfaces and tiled resolve ranges), the pipeline cache and the render configuration at the new scale, reopens the shader storage with that scale's pack, and reloads the guest's active shaders from their microcode. Guest memory and the register file stay. A scale without a prepared pack (or Vulkan) keeps the RESTART badge and applies at the next start. Packs of scales prepared earlier stay in the cache under their own names. The new PREPARE ALL SCALES setting (`pinyon_shift_prepare_all_scales`) makes graphics preparation produce the other scales' packs up front, each keyed as if it were the chosen scale. Prewarm now skips the few variants a pack lacks instead of dropping the whole catalog. `fh1-scale-switch` (new `cvar` route command, `--shader-pack` repeatable) switches free roam from 1x to 2x and back in 1173 and 1096 ms, with captures of 1280x720, 2560x1440 and 1280x720, no GPU errors and a 2x pack produced for it. The title pauses for that second, so the route has no simulation-time check. | L |
| NP-4.8 | Recorded decisions, not scheduled: non-integer or dynamic scale (architectural), a true wider back buffer (predicated tiling bands, every resolve kind, thumbnails; only if Hor+ shows unacceptable artifacts), HDR output (the guest tonemaps to SDR; plumbing is M, quality is L). | — |
| NP-4.9 | Change the resolution scale live on every backend without new shaders or a restart. Today each scale is its own shader pack (the scale is baked into the translated shaders as a modification bit and into the pack name), so NP-4.7 switches in about a second only when that scale's pack was prepared, and Vulkan waits for a restart. Make the scale a runtime value instead: compile one general set of shaders, pass the scale through the system constants (or push constants on Vulkan) with the scaled-texture and resolve paths reading it, and rebuild only the scale-sized resources (surfaces, resolve ranges) on a switch. Gate: a 1x to 2x to 4x to 1x round trip on D3D12 and Vulkan with one pack, no misses, and the golden replays unchanged at 1x. | L |
| NP-4.10 | **The speed part (3x and 4x GPU cost, the catch-up bursts) moved to the [performance backlog](PERFORMANCE_BACKLOG.md) on 2026-09-30; the window and shadow artifacts stay here.** Higher scales on D3D12, from the 2026-09-30 play test: at 2x, random pink flashes on the cars' rear windows; at 3x, bright green edges around the rear windows and artifacts in the cars' shadows, and the game feels slower and heavier; at 4x it is very laggy and the simulation misbehaves, at times speeding up as if catching up. The window artifacts may share a cause with the Vulkan glow fixed in NP-12.4 (the car glass and paint shaders, their cube fetch and HDR math) or with scaled resolves of the car reflection and shadow maps, so first compare 1x, 2x and 3x frame dumps of the same car. For 3x and 4x, measure the GPU and CPU frame against 1x (the scaled resolve and transfer costs grow with the square of the scale), and check how the title's simulation reacts to frames longer than its step: the catch-up bursts point at the delta clamp in the main loop (`owner+448`), which should cap the steps per frame instead of replaying lost time. | M |

**Gates.** 21:9 and 32:9 show more world horizontally with no distortion and
the HUD at the edges; 16:9 output is unchanged under golden replay; 2x on 4K
and 3x on 1440p pass a sharpness comparison against the pixel-exact case;
the 4x pack runs the race, free-roam and map routes with zero misses and the
memory budget logged; caps honoured within the distinct-presentation
tolerance.

## NP-5 Native profile, achievements, dialogs, language

| Item | Work | Size |
| --- | --- | --- |
| NP-5.1 | **Done** (SDK `7ca8128`): `user_name` (sanitised to an Xbox gamertag, restart) replaces the fixed "User" and FH1 reads it through `XamUserGetName`; `user_gamerpic` fills `XamReadTileToTexture` tiles from a PNG or JPEG. The XUID and save directory stay fixed. Profile edits the gamertag one letter at a time (LETTER, POSITION, DELETE, SAVE) so the pad works as well as the keyboard. Where FH1 shows the name in-game is not yet confirmed | S–M |
| NP-5.2 | **Done** (SDK `165d1b8`, project `2fd9ec4`): `rex::kernel::xam::XamUiProvider` lets the host replace the ImGui message box and keyboard; the dispatcher keeps the `XN_SYS_UI` notifications, the `XamIsUIActive` count and the overlapped completion, and B or Escape completes with `X_ERROR_CANCELLED`. The host UI draws both in the game's fonts: wrapped text under the title, buttons as rows, and a keyboard edited with the pad (letter, position, delete) or by typing. `fh1-xam-dialogs` (sample dialogs through `xamdialog` route steps): chosen button, cancel, edited text and cancel all return as expected, layouts inside the safe area. `XamShowMessageBoxUIEx` stays a stub (FH1 imports it; no call seen yet). `pinyon_shift_host_xam_dialogs=false` keeps the ImGui dialogs | M |
| NP-5.3 | **Done** (SDK `9acbcbd`, project `66882bf`): F7, SETTINGS > ACHIEVEMENTS and the title's `XamShowAchievementsUI` (a stub until now) open a host list with gamerscore or LOCKED per achievement and the focused one's description; unlocks show a host toast with the title's XDBF icon; the ImGui overlay and toast are no longer created. Unlocks keep the TOML store. Checked by `fh1-host-features` (toast shown, list opened and closed by the provider and by F7). No unlock sound | S |
| NP-5.4 | **Done** (SDK `90285fd`, `a153034`): FH1 reads the console language and country through `ExGetXConfigSetting` (`user_language`, `user_country`) and mounts all 22 `stringtables` archives, loading the `.str` tables of one. A title-screen probe of 22 pairs (`.local/np54/probe.sh`) found the pair for each of the 20 player tables: EN (1,103), GB (1,35), FR (4,34), DE (3,24), IT (6,50), ES (5,31), MX (5,71), BR (9,13), NL (16,74), DA (1,25), NB (15,75), SV (13,90), FI (1,32), PL (11,82), CZ (1,23), HU (1,42), RU (12,88), JP (2,53), KO (7,56) and CHT (8,101); PROFILE > LANGUAGE offers them (restart). `XGetLanguage` now returns `user_language` and the language enum covers 13-17. Japanese, Korean and Chinese text use a vertex shader the English preparation never sees and that was not even in the analysis catalog, so it failed without being recorded; such shaders are now recorded as misses, so one session in those languages feeds the next preparation | M |
| NP-5.5 | **Done** (project `66882bf`): `src/save_backups.cpp` copies the state's `user` directory to `backups/saves/<UTC>` at each session start (when it differs from the newest backup) and after every save once its files have been still for a poll interval, keeping `pinyon_shift_save_backup_slots` (10). PROFILE > SAVE BACKUPS lists them and schedules a restore, which is applied at the next start before the title runs, after the current files are backed up as `before-restore`. Checked on a private state: a session backup of 19 files, a restore scheduled from the settings screen, and a relaunch that applied it with identical file hashes and no staging directories left | S–M |
| NP-5.6 | **Done**: F8 (`bind_photo`) captures the title's image at the internal resolution without host overlays and writes `<state>/photos/pinyon-shift-<UTC>.png` on a background thread (logged as `photo.saved`). The PNG encoder is self-contained (`src/ui/png_writer.cpp`: adaptive None/Sub/Up filters, fixed-Huffman deflate); its output was checked against Python's zlib and CRCs, and a free-roam route pressing F8 wrote the frame | S |

**Gates.** A guest `XamShowMessageBoxUI` shows the host-styled box and
returns the chosen index; `XamShowAchievementsUI` opens the list and returns
after close; booting in German, French and Japanese shows a localised pause
menu with achievement strings following; the gamertag appears where the game
renders it; a restored backup loads and the original file hash is unchanged.

## NP-6 Input

| Item | Work | Size |
| --- | --- | --- |
| NP-6.1 | **Done** (SDK `1167b52`): `pad_remap` maps each physical control (buttons and triggers) to the control the title receives as `PHYSICAL=GAME` pairs, and `pad_invert_right_stick_y` inverts look; CONTROLS > CONTROLLER BUTTONS edits them live. Only the title's reads are remapped: host menus keep the physical layout, so a remap cannot lock the player out of the remap screen. Mouse and keyboard keep their keybinds. `fh1-host-features` with `pad_remap=B=A` reaches free roam pressing only B. Stick-to-stick remapping is not offered | M |
| NP-6.2 | **Done** (NP-1.4): CONTROLS lists the key each pad control maps to in mouse-and-keyboard mode. Keyboard glyphs in the game's own HUD need texture replacement and stay with NP-10.3 | S |
| NP-6.3 | **In part** (SDK `1167b52`): `pad_rumble_strength` (CONTROLS > RUMBLE) scales vibration. Verifying DualSense and Steam Input through SDL and documenting a Deck layout need the hardware (see the human-only list) | S |
| NP-6.4 | **Done** (SDK `e2eb60f`): Controls has MOUSE (off, camera, steering) and MOUSE SENSITIVITY. Steering (`mnk_mouse_steering`) turns horizontal mouse movement into a virtual wheel on the left stick that eases back to centre at `mnk_steering_return` locks per second, with the camera on the right-stick keys | S |

**Gates.** Swapping A and B in the remap screen changes pause navigation and
the race, persists across restart, and the SDL database still resolves
unmapped pads.

## NP-7 Mod host v1

**Design decisions.** Guest addresses are fixed by the supported XEX, so
`config/rexglue/analysis/main-xex.toml` is already an address registry; host
symbols are not stable. Mods therefore link against a versioned C ABI,
semantic names and cvars, never raw addresses or the PPC context. The ABI
adopts the shape the ReXGlue community already uses (`rex_mod_abi_version`,
`rex_mod_create`, `IModPlugin` with `OnCreateDialogs`, `OnModuleLaunched` and
`OnShutdown`, `ModHostContext`, `mod.toml` with `requires`, `load_after`,
`conflicts` and `game_version`, `enabled_mods` ordering) so mods and tooling
transfer between projects, and extends it with Pinyon hook points, the symbol
table and a guest-thread request queue. Runtime DLLs can only replace indirect
calls through the dispatch table; direct calls are C++ calls in the generated
code. The host executable therefore owns a fixed set of hook points and
publishes them.

| Item | Work | Size |
| --- | --- | --- |
| NP-7.1 | **Done** (`c1e0b98`): `frame.tick`, vehicle pose, `save.before_encrypt`, `file.open` and the pause-button site dispatch to subscribed callbacks (free when nothing subscribed); guest tasks drain at `frame.tick` on the main thread through `CallGuestFunction`. The built-in UI experiments still call their code directly: they are test variables, and moving them buys nothing until NP-11.1 | M |
| NP-7.2 | **Done** (`c1e0b98`): `tools/generate-fh1-symbols.py` generates the host table from `config/mod/fh1-symbols.toml` plus every `[[midasm_hook]]` as `hook.<name>`, keyed to the `default.xex` hash; `find_symbol` and `find_offset` read it, and a test fails when the table and the hooks disagree | S |
| NP-7.3 | **Done** (`c1e0b98`): `include/pinyon_mod.h` ABI 1 (append-only, `size`-versioned), loading from `mods/<name>/code/` in `enabled_mods` order after `mod.toml` checks (ABI, `game_version`, `requires`, `load_after`, `conflicts`), never unloaded; guest read and write, `call_guest`, symbols, `subscribe`, guest tasks, cvars, binds, host dialogs and events. `docs/MODDING.md` records the direct-call limitation | M |
| NP-7.4 | **Done** (`c1e0b98`, SDK `8f2d4d4`): an overlay device over the base game device (`ReplaceDevice`, since the VFS resolves the first prefix match) serves loaded mods' `game/` files, earliest mod first, whole files only; each served file logs `mod.file.override` | S |
| NP-7.5 | **Done** (`c1e0b98`, NP-8): with mods or cheats on, the title plays `<state>/user-modded`, copied from the player's profile the first time; every save writes `pinyon_shift_mods.json` with the mods, the active cheats, the mod-set hash and the plaintext body hash. The settings screen shows the modded state on MODS and CHEATS; no schema migration was needed, since `enabled_mods` defaults to empty | S–M |
| NP-7.6 | **Done** (`c1e0b98`, NP-11): `hello_telemetry` (setting, bind, hooks, a guest call, a dialog, a HUD label and a menu action) and the asset-only `english_strings`, `tools/install-sample-mod.py`, `docs/MODDING.md` and the `fh1-mods` and `fh1-mods-ui` routes | S |

**Gates.** A sample DLL adds a cvar, opens a host-layer dialog, subscribes
to `frame.tick`, calls a guest function through the queue and shuts down
cleanly; a replaced `media/stringtables/EN.zip` is observed through the
file-open observer with the stock file untouched when the mod is disabled;
enabling cheats creates `user-modded` and the AppData save hash is unchanged;
`tools/check-markdown-links.py` passes with the new document.

## NP-8 Cheat menu v1

**Cheapest first.** The trainer ships as a first-party mod on the NP-7 hook
registry and profile isolation so the ABI is dog-fooded before third parties
use it; it does not wait for the plugin loader or the asset overlay.
Post-effect toggles and movie skip exist. Teleport and
position freeze use the vehicle-pose hook the project already writes through;
time scale uses the simulation delta the project already observes; career
stage skip reuses the checkpoint seeding that exists as a test variable; the
save-body editor uses the plaintext hook plus the disc's own profile schema.
Credits, XP, wristband, weather, traffic, race state, rewind and camera have
no located function yet and need the discovery programme.

| Item | Work | Size |
| --- | --- | --- |
| NP-8.1 | **Partly done**: `pinyon_shift_cheats` (restart; from the config file or the command line) and the hot `cheat_time_scale` (0.25 to 2, clamped) in a Cheats category; the scale multiplies `f31` in the delta hook before the store at `0x823EDB84`. Measured on free roam: simulation-to-wall ratio 0.503 at 0.5 and 2.010 at 2.0 (1.0 is 0.95 to 1.08). Freeze and teleport are not possible on `0x82BC5A3C`: it is the presentation transform, rewritten from the physics body each frame, so they wait on NP-8.4. The career-intro skip is still to do: the checkpoint seeding it would reuse (`PINYON_SHIFT_M5_TEST_CAREER_CHECKPOINT`) edits the outgoing save and only matches the old 19,472-byte profile, so it belongs on the load-time editor of NP-8.3 and needs a fresh-profile route to test. The state is `CFirstTimeCareerState` in the save's class-serialized tail (`first_time_career_activity`: an active byte, then the stage; stage 1 is the opening Viper race, 2 the Corrado drive to the festival, 7 and 10 later checkpoints the durable-checkpoint hooks restore), outside the self-describing fields `cheat_set_profile_fields` edits, and a new player has no profile to edit until the title's first save, so the skip can only move a saved stage-1 profile to stage 2 at its next load. The title's switches are more than the three named here: `sub_824F8150` reads one token per call (`name` flips a switch, `name=value` sets it, through `sub_82C096E0` and `sub_82C09468`) and knows `forceEnableDebugMenus`, `debugmenudescriptions`, `timeofdayindex`, `highrescubemap`, `frontend30fps`, `mainthread30fps`, `framesperrender`, `maxaicars` and about 60 more (names at `0x82010A2C`-`0x82010D84`); `loadcmdlinedottxt=<path>` and `ignorecmdlinedottxt` (`sub_824E4228`) name a file of more tokens, `GAME:\cmdline.txt` by default. The retail title reads no token source by default: the kernel command line (`cl`) is not imported, and `cmdline.txt` served by a mod is never opened. The parameter object is a lazily built singleton (`sub_82479E88`, pointer at `0x832E2680`) read on demand; feeding `sub_824F8150` host tokens at the first frame tick was tried (`timeofdayindex=3`, `forceEnableDebugMenus`) and changed nothing visible, so each switch's consumer has to be traced before any is offered as a cheat | S |
| NP-8.2 | **Done**: F10 (`bind_trainer`) opens TRAINER on the host layer with PLAYER (set credits, NP-8.3), WORLD (game speed), VEHICLE (freeze and teleport shown disabled until NP-8.4), GRAPHICS (motion blur, depth of field, trilinear) and DEBUG (file-open log); pad, keyboard and mouse navigation; the title pauses into its own pause menu while it is open. Each change logs `cheat.changed`. Cheats stay off until the title plays the isolated `user-modded` profile, and SETTINGS > CHEATS turns them on. `fh1-trainer` drives it | M |
| NP-8.3 | **Done**: the profile body opens with a self-describing section (field count, then `[len][name][0x20][0][type][value]`, structs nested) holding `Main/Credits` (UInt32), `Main/XP`, `Main/Level` and `Main/WristbandLevel`; `tools/fh1-profile.py` decodes, edits and round-trips every captured profile byte-identically, keeping the class-serialised tail raw. The running title keeps money encoded in memory (a scan of the guest heaps finds no plain copy), so an edit to an outgoing save would last one save; the editor instead writes the body the title has just decrypted (a new hook at `0x82C66594` in `sub_82C66308`, also the mods' `save.after_decrypt`). TRAINER > PLAYER > SET CREDITS applies once at the next load and then clears itself. Buy-car from the seed with 1,000,000 set: the showroom shows "Available: 1,000,000 Cr", and the saves after the 120,000 purchase hold 880,000 | M |
| NP-8.4 | Discovery programme: name at least one function with a register contract for credits, XP, wristband, time of day, weather, traffic density, race state, rewind and camera, using trace probes, `gamedb.slt` table names and the existing UI-trace workflow; register each in the symbol table.. Time of day, first lead (2026-09-29): the title's `timeofdayindex` switch (`+2412` of the command-line singleton) is read by `sub_825CEAD0`, which otherwise takes a byte of the event data (`[r27+8]`) and stores the index into its load parameters (`[r1+196]` at `0x825CEBA8`); it runs once as free roam loads, with index 0, and forcing 2 or 3 there leaves free roam's lighting unchanged, so free roam's time comes from elsewhere (the dynamic sky or the save). **Scan tooling (2026-09-29):** routes can now `snapshot` physical guest memory and `poke` floats, and `tools/scan-guest-snapshots.py` lists values that step steadily between snapshots. In free roam (three snapshots 10 s apart) the steady risers in [0, 1] include rotation-matrix elements of a slowly turning object (poking them changed nothing visible) and one clock at 0.4486, 0.4500, 0.4514 (a two-hour cycle, about 10:45 as a day fraction, matching the daytime scene), but the heap layout and timing differ between runs, so that address was not the clock in the next run. Routes can now `mark` the title's virtual heaps (about 110 MB) and `scanpoke` every steady riser in a range within the same run: in free roam, 115 floats in [0, 1] rising 0.0003 to 0.006 per 10 s (a one- to nine-hour day) poked to 0.95 leave the lighting unchanged, poking the 238 in [0, 24] rising 0.005 to 0.2 (hours) or all 402 in [0, 1] crashes the title, and the 82 in [0, 24] rising 0.02 to 0.07 (a one- to three-hour day) are mostly position triples 16 bytes apart (moving objects: poking them moves the car and traffic) with the lighting unchanged. So free roam's sky clock is not a rising fraction or hour count. **Time of day found (2026-09-30):** `FirstTimeCareer.xml` notes that time is `hr * 60 * 60`, and a seconds-range `scanpoke` (40,000 to 50,000, rising 200 to 350 per 10 s) finds five copies at 46,729 s (12:59, advancing 28 game seconds per real second, a 51-minute day); poking them to 79,200 turns free roam to night. From the 86,400.0 constant (`0x8200E704`) back to its users: the time-of-day object is the world's `+232` (`sub_82486CF0`), the world is `[[[0x832DF024] + 4] + 4]` (`sub_8247FC10`, `sub_824AFB20`), its float at `+10488` is seconds since midnight, advanced and lit by `sub_825CB718` each frame, and `sub_825C7DD0` (r3 the object, f1 the target seconds, plus 86,400 to pass midnight, f2 game seconds per second) requests a transition; a set byte at `+10505` means a script holds the time. Registered as `time_of_day.from_world`, `time_of_day.request` and `time_of_day.update`, with offsets `world.time_of_day`, `time_of_day.seconds` and `time_of_day.script_hold`. Weather does not exist in FH1: the executable's only "weather" string is `weatherstrip`, and the sky's clouds are fixed maps in `realtimesky.zip` (`CloudDefs.xml`, `*Cloud*.xds`). **Camera (2026-09-30):** the script functors are registered by name (`sub_828F7180` for `CChangeToFreeCamera`, a factory whose create method builds the action), and following their vtables gives the title's own camera switches: `CChangeToFreeCamera` (`sub_828F2DB0`) sets each of the world's camera controllers (`sub_82486C40` counts them, `sub_82486C70` returns one) to mode 6 with `sub_82858638`, and `CResetCameraToPlayer` (`sub_82937158`) returns each player camera (`sub_82486B40`) with `sub_825A86F8`; registered as `camera.count`, `camera.controller`, `camera.set_mode`, `camera.player_controller` and `camera.reset_to_player`. The same functor route leads to the wristband (`CTriggerWristbandUpgrade`, `CWristbandManager`) and rewind (`CStartRewindReplayFunctor`, `CFinishRewindFunctor`) actions. **Race state (2026-09-30):** the wristband action below checks a game mode, `sub_824878D0` (r3 world, returns `[[world + 124] + 56]`). Logged on every change over `fh1-race-retire`, it is 17 in free roam, turns 3 as the event is entered (between the event's first and third menu steps), stays 3 through the race, pause and quit, and is 17 again once the retire returns to free roam; the action also accepts 18. Registered as `world.game_mode` with offsets `world.session` and `session.game_mode`. **Wristband action:** `CTriggerWristbandUpgrade` (registered by `sub_82987978`, factory vtable `0x8208C858`, execute `sub_82989D10`, `this` unused) accepts modes 17, 18 and 3, passes the player's current wristband to `sub_824CD660` and requests `GAME:\Media\UI\Videos\WristbandGet.wmv` (see NP-2.9). Calling the execute from a host task in free roam changes nothing visible, so it is not offered as a cheat; TRAINER > PLAYER > SET WRISTBAND stays the way to change wristbands. Still to name: XP at run time, traffic density at run time (mods set it at load through NP-10.2) and rewind | L, ongoing |
| NP-8.5 | Follow-on cheats as NP-8.4 lands: freecam, infinite rewind, traffic density, time-of-day and weather lock, unlock all cars and events. **Wristbands and profile fields done** (2026-09-30): `cheat_set_profile_fields` (restart, once, like the credits) sets any scalar field of the profile at its next load as `Path/Name=value` pairs, and TRAINER > PLAYER > SET WRISTBAND offers levels 1 to 8; buy-car with `Main/WristbandLevel=8,Main/XP=450000` keeps both values in the title's own later saves, and the event card's goal changes from COLLECT BLUE WRISTBAND to GET TO THE HORIZON FINAL, so the events the wristbands gate open. Rewind needs no cheat: FH1's rewind is an assist with unlimited uses (its `RewindCoolDown` tunable only paces the first-career hint). **Free camera done** (2026-09-30): TRAINER > WORLD > FREE CAMERA (`cheat_free_camera`, hot) runs the title's own switch as a host guest task (a new `EnqueueHostGuestTask` and `CallGuest` beside the mods' task queue) and switches back with its reset-to-player action; `fh1-free-camera` (cheats on) shows the free camera above the car, the left stick flying it away from the parked car, and the chase camera back when it is turned off. **Time-of-day lock done** (2026-09-30): TRAINER > WORLD > TIME OF DAY (`cheat_time_of_day`, hot, RUNNING or 00:00 to 21:00) holds the clock at that hour by writing the time-of-day object's seconds once per frame from the delta hook, following the world chain of NP-8.4 with readability checks and leaving a script-held time alone; free roam with 22:00 renders at night from the first capture. Traffic density is available to mods through NP-10.2's merge of `AIOpenWorld.xml`; a weather lock does not apply (FH1 has no weather, NP-8.4) | S each |
| NP-8.6 | Cheat menu v2, beyond the NP-8.5 follow-ons: ADD CREDITS (an amount on top of the balance, not only a set value), unlocks (cars, events, upgrades, paints and other progression gates) and map markers for collectibles: the hidden discount signs, the barn finds and the other findables, shown on the map and optionally on the minimap, with a found/not-found state read from the profile. Needs the collectible tables and their profile flags named first (NP-8.4 method: script functors, `gamedb.slt` tables, profile fields), then the map-icon path of the title's UI. | M–L |
| NP-8.7 | REMOVE CAR LIMITS: let any owned car enter any event, ignoring its class, manufacturer or other restrictions (a cheat, off by default, marked in the event card). Needs the event entry check found first (the event data's car restriction fields and the function that filters the garage for an event), following the NP-8.4 method. | S–M |

**Gates.** The trainer opens and closes 20 times in free roam with no leaked
input and no guest call from the UI thread (asserted); teleport to five stored
points with the camera following and no discontinuity storm in vehicle
telemetry; an edited credit value survives a save, reload and UI display on
the isolated profile; the race route still passes with cheats off.

## NP-9 Fast frame, pass 2

**Why after NP-2 and NP-3.** These are the rewrites that make the race
window GPU-bound and that the Vulkan executor in NP-12 depends on. NP-9.0
comes first because the resolve work rewrites the executor, and the
portability assessment wants the API-agnostic core proven behaviour-preserving
on Windows before it gains a second consumer.

| Item | Work | Size |
| --- | --- | --- |
| NP-9.0 | **Done** (SDK `8aeca55` to `49bb288`): the FH1 executor's API-agnostic core is in `rex::graphics`: `Fh1EdramTiles` (tile owners, stencil state, claims that return what to transfer, `SplitByOwner` for resolve sources), `Fh1SurfaceKey` with the pitch and height rules, `Fh1PlanResolve` (resolve rectangle, supported formats, the copy plan), `Fh1DepthOverwrite` (depth-overwrite rectangles from the CPU-interpreted vertex shader, with `Fh1DrawInfo`) and `Fh1ExecutorCounters`. The D3D12 executor keeps resources, views, pipelines, barriers, transfers, resolve copies and read-backs. Every step replayed the four golden frames byte-identically, and `fh1-race-sync` passes; `pinyon_shift_fh1_edram_tiles_tests` covers the tile and surface core | M |
| NP-9.1 | **Superseded by [PB-1.2](PERFORMANCE_BACKLOG.md#pb-1-gpu-at-3x) (2026-09-30): at 3x the reloads cost about 2.6 ms of GPU per frame.** Measured, deferred at 1x. Resolve output aliasing (resolving straight into destination textures, binding native-written ranges, presenting the front buffer from the native surface) would remove the untile pass of resolve-sourced texture reloads. Measured on `fh1-race-sync` (1x, race window, median of 600 frames, SDK `c50dc1d` adds `texture_resolve_reload_cpu_time_ns`): 87 resolve-sourced reloads per frame cost 71 us of GPU commands thread CPU, and NP-2.0 measured 0.39-0.56 ms of GPU for them against a 15.4 ms guest-frame GPU span at 59 fps. The mirror write must stay (the CPU, other aliasing textures and memexport read guest memory), so aliasing would add a second write per resolve or need format-cast UAVs over every resolvable texture format to save at most about 0.5 ms of GPU; the front buffer's own round trip is 3.7 MB a frame. Not worth the risk to the executor's correctness now; revisit if 4x scale or a slower GPU makes resolve reloads a measured bottleneck. | L |
| NP-9.2 | **Superseded by [PB-2.11](PERFORMANCE_BACKLOG.md#pb-2-gpu-commands-thread-on-vulkan), the decode-to-record split (2026-09-30).** Decided, not adopted at 60 fps. NP-2.6 chose overlap, and direct recording is the alternative it rejected: the tape costs the GPU commands thread one small append per D3D12 call, while recording directly would put each call's runtime and driver time back on that thread, the race frame's bottleneck (the replay the worker now runs is 3.44 ms median, 5.46 ms p95 per race frame; synchronous submission, tape plus replay on one thread, measured 21.05-21.19 ms against 19.25-20.32 ms overlapped). Removing the tape would only pay if recording itself moved to several threads, which is NP-9.3. | M |
| NP-9.3 | **Superseded by [PB-2](PERFORMANCE_BACKLOG.md#pb-2-gpu-commands-thread-on-vulkan) (2026-09-30): the thread must drop from about 18 to 6 ms.** Measured; parallelism deferred, single-thread fixes taken (SDK `d0ec976`, `116e912`, `242aa60`; project `d2f66ec`). New per-frame counters split the GPU commands thread's frame into waits ([baselines](native-renderer/NATIVE_PERFORMANCE_BASELINES.md#at-the-60-fps-cap-np-93)), and `pinyon_shift_thread_sampler` profiles it without an elevated shell ([guide](native-renderer/CPU_HOTSPOT_PROFILING.md#sample-one-thread-without-administrator-rights)). On `fh1-race-sync` the race now runs at the title's 60 fps cap (16.7 ms median, about 17 ms mean, p95 about 20 ms). The RTX 4080 is 35-47 % utilized, and the thread is busy about 86 % of the frame: 0.1 ms waiting for the title, 1.5 ms in `WAIT_REG_MEM`, 0.5 ms on fences. So it makes the frames that miss the cap, and the title rarely starves it. Its time is spread: draws 47.5 % (`UpdateBindings` 10.4, texture requests 8.1, shared-memory ranges 7.0, primitive processing 5.4, executor targets 5.4 %), type-0 register writes 16.7 %, PM4 dispatch 9.6 %, swap 8.7 %. A decode-to-record pipeline could take at most the register writes and dispatch (about a quarter) off the thread. It would need a register-write log replayed on the recording side, and ordering for `WAIT_REG_MEM` (it polls memory the title writes), `EVENT_WRITE_SHD` stores the title polls, and write-watch invalidation before `RequestRanges`. Parallel draw preparation needs per-draw register snapshots. Neither is worth that risk while the thread holds 60 fps with about 14 % spare; revisit with the sampler on a machine that misses the cap. Taken instead: `WAIT_REG_MEM` yields for up to 2 ms before its 1 ms-minimum sleep (`wait_reg_mem_yield_us`; three interleaved pairs, 16.76-16.92 against 17.05-17.23 ms mean), and the executor's per-draw CPU phase timers run only with `fh1_native_gpu_profile` (within noise). | L |
| NP-9.4 | **Done** (SDK `597fad7`): `rex::graphics::Fh1ShaderPack` reads format v3 ([pack contract](native-renderer/SHADER_PACK_FORMAT.md)), named `4D5309C9.fh1-native-v3.<backend>.<features>.<flags>.<scale>.pnsp`: the header holds the backend (DXBC or SPIR-V, checked against each entry's magic) and the device features that change translation (D3D12: switch statements, which the translator avoids on Intel) instead of the GPU vendor, so NVIDIA and AMD share a pack; the loader hashes with CNG on Windows and the vendored SHA-256 elsewhere. Entries gain a geometry stage keyed by the geometry shader key: for each vertex translation it captures, the producer writes the keys pipelines drawn with it can take (rectangle and quad lists, points with and without point coordinates; 44 at 1x), and `GetGeometryShader` takes them from the pack, so `CreateDxbcGeometryShader` and `DXBCChecksum.cpp` are producer-only (the runtime keeps `pipeline/shader/dxbc.h` for its binding types). A runtime geometry miss is logged, recorded as `geometry-0000000000000000-<key>.bin` for the next production and fails the pipeline. `native-shader-pack.py`, the capture manifest (schema v3), its tests and the loader test cover both backends and the geometry stage; production and `launch-preview.ps1` now also work from a RelWithDebInfo build. Evidence: the four golden replays are byte-identical with zero pack misses on a v3 pack holding the goldens' shaders plus the produced geometry shaders, and a fresh v3 production (24,783 entries, 529 MB) passes its strict route. A fresh production does not reproduce the goldens' exact shader set (37 of their 24,736 variants come from runs the preparation route does not repeat), so replays need the pack they were recorded with. | M |
| NP-9.5 | **Superseded by [PB-2.12](PERFORMANCE_BACKLOG.md#pb-2-gpu-commands-thread-on-vulkan) (2026-09-30), the third tier of the GPU commands thread work.** Earlier decision, not now. A native draw ABI would replace the per-draw register-to-`PipelineDescription`, `SystemConstants` and `UpdateBindings` derivation with a native contract. The pack would stop targeting Xenia's constant-buffer and root-signature layout, which needs a new translator output. This is the real boundary between "Xenia backend with native surfaces" and a native renderer. NP-9.1 and NP-9.3 measured what it would save. On the race's bottleneck thread the derivation is about 16 % of wall time: `UpdateBindings` 10.4 % (float constant gather 3.3 %), `ConfigurePipeline` 3.2 %, system constants and state description about 2 %. Resolve round trips cost at most 0.5 ms of GPU. The race holds the 60 fps cap with about 14 % of that thread spare, so an XL translator and pack change for at most a sixth of one thread is not justified now. Revisit when a supported machine misses the cap with the GPU commands thread as the limit (measure with `pinyon_shift_thread_sampler`). | XL |

**Gates.** Race window median at or below the GPU span plus 2 ms on the
baseline machine; resolve-sourced fetches served without an untile dispatch
on `fh1-race-sync` and `fh1-free-roam`; golden replays within tolerance;
`fh1-buy-car` thumbnail real at 1x and 2x; no new executor skip reasons; the
pack format version bumped and documented.

## NP-10 Content mods

| Item | Work | Size |
| --- | --- | --- |
| NP-10.1 | **Done** for archive members (the UI scene stream adapter is not needed for it): `tools/build-mod-archives.py` rebuilds each archive a mod changes from the player's copy, copying untouched members' headers and LZX bytes, storing replacements (method 0), updating each record's data-offset extra field (id `0x1123`, the absolute offset of the member's data, which the title reads) and the archive's `zipmanifest.xml` line (`dirsize` includes the end record), as the generated mod `zz-archive-patches`; `launch-preview.ps1` runs it. An unchanged rebuild reproduces 120 of 120 stock archives byte for byte; the one archive whose end record disagrees with the manifest (the 230,057-entry track `bin.zip`) is refused. The title checks a verified file's size against its table in `sub_82C03E90`, so a hook at `0x82C041A4` accepts the real size for files a mod replaces (with the block-hash hooks of NP-10.2). `fh1-pause` with a mod replacing only `EN.zip/PauseMenu.str`: QUIT reads EXIT, no dirty-disc error | M–L |
| NP-10.2 | **Done** (`9e87011`; merges 2026-09-30): the title opens `media/db/gamedb.slt` loose, so no repacker is needed; `tools/build-mod-patches.py` applies enabled mods' `db/*.sql` in load order to a copy of the player's database, served as the generated first-priority mod `zz-db-patches` (removed when no script is left), run by `launch-preview.ps1` before each start. The title reads the file through a block reader that checks each block against a SHA-256 table for the original (`sub_82BFFDA0` from `sub_82C05530`) and raised the dirty-disc error; two hooks on the check's result accept a mismatch only for files a loaded mod replaces. Verified: a mod setting the Jaguar XKR-S (`Data_Car` 1496) to 1,000 shows "1,000 Cr or 1 Token" in the showroom; without it, 120,000. Merging by key (on NP-10.1's archive rebuild): a mod ships only the settings it changes under `mods/<name>/merge/<archive>/<member>`; `.ini` members (`Section\Key value`) merge key by key and `.xml` members element by element (tag plus `id`, `name`, `model`, `key` or `type`, else position; `pinyon-remove`), over a replaced member or the player's own (LZX members decompressed with `pinyon_shift_fh1_archive_extract`, which `launch-preview.ps1` passes), the earlier mod winning a key two mods set. Free roam with two mods merging `AIOpenWorld.xml` (no traffic), `GameTunableSettings.ini` and both into `PhysicsSettings.ini`: both archives rebuilt, `mod.file.hash_accepted` for each, no dirty-disc error, the merged members hold the expected values with comments and CRLF kept, and the traffic car of the baseline capture is gone | M |
| NP-10.3 | **Done** (SDK `d19ff4a`, `a13808b`): the D3D12 texture cache's CPU load hook dumps DXT1, DXT3 and DXT5 2D textures as `<hash>.dds` (`texture_dump_dir`; XXH3 of the guest base level, untiled on the CPU with every level guest memory holds) and uploads a `<hash>.dds` of the same size and format with at least as many levels instead of the guest data (`texture_replacement_dirs`); loaded mods' `textures/` folders are passed to it in load order. Free roam: 664 dumps (568 DXT1, 96 DXT5) decode correctly, and recolouring all of them shows 634 replacements in the captures (road, terrain, trees, lamps, HUD); a mod folder works the same way. Higher-resolution replacements (SDK `9ca083e`): a replacement 2x, 4x or 8x the guest size draws from a resource of its own with the guest's levels plus the larger ones, the texture switches back to its guest-size resource when new guest data has no replacement, views of both live until the texture is destroyed, and a switch bumps a generation the cached descriptor tables compare. Free roam with the 664 dumps upscaled 2x (block indices remapped, red and blue swapped): 629 replacements at 2x (up to 1024x1024), captures correct, golden replays unchanged. Reload in place (SDK `3244233`): SETTINGS > MODS > RELOAD TEXTURES bumps `texture_replacement_reload`, and the texture cache rescans the folders at the next frame and clears the GPU caches through `ClearCaches`, so every texture reloads; a route that reloads in free roam rescanned 664 files and reapplied them. Formats (SDK `4c511d9`): DXT5A (BC4), DXN (BC5) and 8_8_8_8 dump and replace too (block helpers take the block width; 8888 uses a DX10 header), and resolve-sourced loads never take a replacement (guest memory may not hold the GPU's output; a replaced texture returns to its guest resource). A free-roam dump holds 565 DXT1, 107 DXT5, 32 DXN, 10 DXT5A and 12 8888 textures; replacements of the new formats (flat DXN, full DXT5A, 8888 at 2x) applied 51 of 54, visible in the captures. Remaining formats are render targets, not assets | L |
| NP-10.4 | **Decided: not now** (2026-09-30, delegated to the agent). Native plugins (NP-7) and data mods (NP-10.1 to 10.3) cover what mods do today; a Lua VM would add a vendored dependency, a sandbox and a second API to keep stable while the UI API (NP-11) is still moving. Revisit when NP-11 settles and modders ask for scripting; the plan stays: Lua 5.4 bound to the mod ABI (symbols, hook points, cvars, guest queue) from `mods/<name>/code/*.lua`, with a per-tick overhead budget. | L |

**Gates.** One tunable XML member and one `.bgf` overridden without whole
archive replacement; a modified `Data_Car` row visible in-game and stock
restored when disabled; one car card texture replaced and rendered correctly
at 1080p and ultrawide.

## NP-11 UI extension API, production

| Item | Work | Size |
| --- | --- | --- |
| NP-11.1 | **Partly done**: the host-layer backend for additive widgets is in the ABI: `set_hud_text` labels drawn over the title in its fonts (1280x720 layout, safe area) and `add_menu_action` rows in SETTINGS > MOD ACTIONS, logged as `mod.menu_action`; `fh1-mods-ui` drives both. The semantic component registry and scene lifecycle of the UI API plan wait on NP-11.3 for anything that edits the title's own scenes | M |
| NP-11.2 | **Done**: string overrides keyed by table and 16-bit entry key (`pinyon_shift::ui::SetUiString`, the mods' `set_ui_string`). A hook on the LSB2 reader's allocation (`0x82CAC704` in `sub_82CAC5B8`) gives tables with overrides room after the pool; the chunk hook writes a replacement in place when it fits, otherwise appends it, points the entry at it and moves the sentinel. The pause SETTINGS label now uses it. `tools/fh1-strings.py` lists a table's keys and text. `fh1-pause` with `hello_telemetry`: PHOTO MODE (10 characters) reads "PHOTO MODE (F8 SAVES A PNG)" (27, appended) and the row art stretches to fit; SETTINGS still replaces MULTIPLAYER | M |
| NP-11.3 | Native insertion research: recover how the animation loader registers a cloned owner's scaler bindings in `sub_8281BBA8`; only connect `AddMenuItem` to the native backend after the eight-row acceptance test passes. Runs in parallel and may never converge; nothing else depends on it. | L |

**Gates.** The plan's production-adapter checklist is green;
`pinyon_shift_fh1_ui_api_tests` extended; a sample mod adds a HUD widget and a
pause action without touching guest addresses.

## NP-12 Linux and Steam Deck

Ordering follows the portability assessment: Linux x86-64 isolates the one
hard problem, graphics, from any CPU-architecture risk, exercises the POSIX
layer that already exists, and targets RADV, the driver with the fewest
feature gaps. Build a Vulkan-native executor on the existing base-class seams;
do not introduce a general RHI.

| Item | Work | Size |
| --- | --- | --- |
| NP-12.1 | **Done except the Linux configure** (`98faefe`): `linux-amd64` Debug, RelWithDebInfo and Release presets; the generator is found in the SDK's `out/<os>-<arch>/Release` for the build host (overridable as `PINYON_SHIFT_REXGLUE_CODEGEN`); `-fasync-exceptions` and `/Brepro` were already Windows-only; non-Windows builds link Threads and `dl`; the AMD64 baseline check runs on every OS. Verified by the Windows reconfigure and build; configuring on Linux waits for a Linux toolchain (see Needs a person). | S |
| NP-12.2 | **Done, POSIX parts unbuilt** (`156c989`): `src/platform/host_platform.h` holds atomic file replacement (write-through `MoveFileExW` on Windows, `rename` elsewhere), UTF-8 environment reads, the executable path, process and thread IDs, fatal-error messages, immediate exit, the display refresh rate and SHA-256 (the SDK's vendored `thirdparty/crypto` on every host, replacing CNG in shader capture). `Windows.h` is out of the app and every source outside the Windows files. The crash reporter is behind `crash_reporter.h`: the Windows minidump reporter moved there unchanged (`-CrashSelfTest` still writes the dump and text report), and `crash_reporter_posix.cpp` handles the fatal signals on an alternate stack and writes the signal, faulting address, program counter and backtrace. Host tests, 177 tool tests and `fh1-scale-switch` pass on Windows; the POSIX sources compile once a Linux toolchain exists. | S–M |
| NP-12.3 | **Done** (SDK `d92731e`): with `REXGLUE_USE_VULKAN=ON` (next to D3D12, on Windows) every Vulkan source compiled; only linking failed, because the runtime SPIR-V translation needs the shader translator and ucode analysis, which were built only into the D3D12 pack producer with the translator core compiled out elsewhere. Vulkan builds now carry them (`REXGPU_SHADER_TRANSLATOR`), and `rexgpu-fh1` links with both backends; the D3D12-only game and producer still build. Running FH1 on Vulkan waits for NP-12.4's executor | M |
| NP-12.4 | **Done** (1x SDK `637644c`, `e57ce81`; 2x, the loss and the glow below): `vulkan::Fh1NativeExecutor` runs FH1 on Vulkan over the NP-9.0 core: surfaces are images with layout tracking, EDRAM tile ownership moves with transfers (color passes, EDRAM words by compute and the nine depth and stencil passes), clears, resolves by compute into the shared memory buffer and one-off readbacks, all with the D3D12 shaders as SPIR-V (constants as push constants, stencil read from R). Guest draws render with dynamic rendering into the surfaces the executor binds, and pipelines take its render pass key; `vulkan_fh1_native_executor` (on) falls back to the render target cache without dynamic rendering or above 1x. The dark world had one cause, found by dumping frame 1700's resolves on both backends (`fh1_resolve_dump_dir` and the new `fh1_resolve_dump_frame` now work on Vulkan too): the first divergence was the reflection cube's mip chain, and the SPIR-V translator read the texture exponent bias from fetch word 4 (the LOD bias) instead of word 3, so every biased HDR fetch came out several times too dark. With that fixed, `fh1-free-roam`, `fh1-race-sync` (12.5 M draws, 233,091 resolves, no skips) and `fh1-buy-car` pass on Vulkan with captures matching D3D12 (the render target cache path renders too, with a green glow on one car). Race window 29 fps (34 ms) against 59 on D3D12, with shaders translated at runtime until NP-12.6. **Later 2026-09-29:** 2x to 4x run on the executor (SDK `e781ab9`): resolves write the scaled resolve buffer, one-off captures also go to guest memory; `fh1-free-roam` passes at 2x with no executor skips. Frame dumps recorded on D3D12 replay on Vulkan (`11bd667`; `test-fh1-frame-replays.py --build-directory out/build/win-amd64-vulkan --game-argument=--gpu_backend=vulkan`); the four goldens match D3D12 but for sparse edge samples. The green glow is reproduced deterministically by a D3D12 dump of free-roam frame 1800 replayed on Vulkan, and bisected with the new `fh1_debug_skip_draws`, `fh1_debug_null_fetch` and `fh1_debug_log_draws` (`f333767`). Two draws make it (SDK `e0f0282` lets the skip cvar take several ranges and makes the null cvar really bind a null texture, which it did not while `gpu_allow_invalid_fetch_constants` is on): the traffic car's glass (draws 2930 and 2931, pixel shader `410E568A69EC236A`, vertex shader `52C709690D1E2418`) and its paint (draw 1761, pixel shader `BDA312E0D00025E9`, vertex shader `A35FE25C28B66413`); with all three skipped 79 of 1,384 green pixels are left. Both draw into the 7e3-as-16 HDR target, whose bloom resolves (draws 2966 to 2968, to `0x1C621000`) spread the glow; there the Vulkan words have green saturated (at least 4.0) where D3D12 has about 0.15. Ruled out: every texture of both shaders (nulled, including the reflection cube, whose resolved faces and mips are identical to D3D12), mip selection (LOD bias of -15 or +3), texels the load leaves unwritten (textures cleared first), anisotropy, a resolve race (the GPU synced after every resolve), the executor (the render target cache path glows too), and the cube instruction and cube fetch translation (identical to DXBC). So large finite values come out of those two shaders' arithmetic on their interpolants and constants on Vulkan only; the next step is a full-resolution capture of their registers (a temporary SPIR-V output override, captured through the half-resolution bloom resolve, was too coarse to name the instruction). The sampled race profile (thread sampler) puts Vulkan's race frame at 31.5 ms against 16.7 on D3D12: the command buffer replay into the driver runs inline on the GPU commands thread (34 %, where D3D12 has a submission worker) and presenting waits on earlier submissions (10 %); a per-draw cvar lookup was removed (`cf58310`) and TEXTURE DETAIL now applies on Vulkan (`2c22476`). Then (SDK `62fca3b`, `8b14b5c`, `37a0efa`): a Vulkan submission worker replays and submits command buffers off the GPU commands thread, as on D3D12, but the race stayed at 31.9 ms because the GPU was the limit (99 % busy against 35-47 % on D3D12). `fh1_native_gpu_profile` now works on Vulkan and showed the executor's transfers, resolves and clears at only 2.4 ms of that GPU frame. Counting render passes and barriers found the cause: every draw put its targets through an attachment-to-attachment image barrier, so each of about 4,850 draws per frame ended its dynamic rendering, waited on a pipeline barrier and began a new one. Surfaces already attached to the draw's open rendering now need no barrier. The frame has 297 renderings and about 600 barriers, and the Vulkan race median is **19.6 ms** (was 31.9); the Vulkan frame replays are byte-identical. Frame dumps now record on Vulkan too (SDK `ccd18f2`: one backend-neutral recorder with a D3D12 and a Vulkan mirror for the GPU-side ranges); a Vulkan free-roam dump replays on Vulkan with no differing words and on D3D12 within 8 of 1023 per channel. At 2x the race route now gets past the event entry but loses the Vulkan device in the race window (0xC0000409 after the presenter's submit fails; NVIDIA event 153, a GPU hang), while 2x free roam passes. The loss is not the submission worker, the attachment barrier change, the executor (the render target cache path loses it too), sparse shared memory, a sparse scaled resolve buffer, texture cache memory limits or VRAM (6 of 16 GB at peak). `vulkan_diagnostic_checkpoints` (SDK `ede75fe`) marks the stream and logs where the GPU was: the point moves between runs, in frames 3060 to 3950, sometimes at a draw and often right after a DXT texture load's dispatches with 200 to 300 draws begun past it. A real overread it led to is fixed (`21fde23`: a scaled texture level's copy took the image size, one texel larger than the loaded data at odd sizes) but was not the loss. After the barrier fix the Vulkan race is bound by the GPU commands thread (a full core, about 3.9 G cycles per second): draws take 59 % of it and `UpdateBindings` 16 %, of which the driver's descriptor allocation and writes are 40 % and the constant packing a third. Reusing a frame's texture descriptor set while its views and samplers are unchanged made no difference (textures change between most draws) and was not kept; dynamic uniform buffers or push descriptors, which move descriptor work into the recorded stream, are the next step. **2x race loss fixed** (SDK `62f61a5`, `18ddfe9`): the checkpoints now record what each marker is, the pixel textures each descriptor write binds and every texture destruction, which pinned the hang to one command, a draw of the car shader `8659BF30B3CBBBA5`. Skipping its draws, or nulling its `tf3`, stopped the loss; nulling its other textures, a LOD bias, turning off the submission worker or the executor did not, and no view it bound had been destroyed. The shader jumps over a predicated cube fetch with `(!p0) jmp`, and `tf3` decides `p0`. The SPIR-V translator jumped per invocation, which split a pixel quad between iterations of its program-counter loop, so the cube fetch's coarse derivatives in the lanes that stayed waited on lanes parked in the next iteration and the NVIDIA GPU hung (sampling the cube at an explicit LOD also passed; zeroing non-finite gradients did not). Xenos takes a predicated jump for all 64 invocations at once and predicates the skipped instructions too, so a predicated forward jump in a pixel shader is now taken only when the whole quad takes it (two quad swaps, where the device has fragment quad operations). The 2x race passes twice on Vulkan, the 1x race and free roam pass, the Vulkan frame replays are byte-identical and the D3D12 ones 4/4. **Glow fixed** (SDK `9e34a49`): the D3D12 runtime only runs precompiled packs, so the shader producer DLL (which translates DXBC at a pack miss) stood in for it with the paint shader forced to a miss, and both translators got a temporary capture that writes one register component after a chosen instruction to the color output. Replaying free-roam frame 1800 on both backends and comparing the paint's pixels placed the first divergence at the reflection-cube fetch (`tfetchCube ... tf1`, 256x256, trilinear, mips 0 to 8): its coordinates matched, the fetched color did not, and at any fixed LOD from 0 to 7 the backends matched again. The fetch passes the coarse derivatives of the cube direction as explicit gradients, and for the same gradients Nvidia's Vulkan driver picks other cube levels than Direct3D 12. Derivative-based cube fetches now sample with implicit LOD plus the bias, as the Xenos does. Frame 1800's green-glow pixels go from 1,384 to 0 (glass and paint), the race at 2x and 1x and free roam pass on Vulkan, the D3D12 replays stay 4/4 and the Vulkan replays are no further from the D3D12 goldens. Not ruled a cause, but tested on the way: denormals (flushing every result changed nothing) and the float-constant upload (identical to D3D12). Left as optional performance work: moving descriptor writes into the recorded stream (dynamic uniform buffers or push descriptors). | L |
| NP-12.5 | **Shaders done** (SDK `0e900eb`): `compile-fh1-native.sh` also writes `vulkan_spirv/` headers for the 64 native-executor shaders and the two texture-cache compute shaders (reflection-cube import, scaled 32-bpp; the unused direct-texture variant is left out). The Windows SDK's DXC has no SPIR-V code generation, so the script runs the vendored glslang's HLSL front end on the same HLSL (`GLSLANG` pointing at a `glslangValidator` built from `thirdparty/glslang` with `ENABLE_HLSL`; no new dependency). Bindings follow the register class in set 0 (b at 0, t at 16, u at 32, `--hlsl-iomap`). All 66 modules pass `spirv-val --target-env vulkan1.1` (vendored SPIRV-Tools), and the DXBC headers are unchanged. The FH1 texture-cache features (reflection-cube import, scaled 32-bpp, linear video upload) are D3D12 fast paths; the generic Vulkan texture cache loads those textures correctly (NP-12.4's routes), so porting them waits for Vulkan performance work. | S + M |
| NP-12.6 | **Done** (SDK `1d28f5c`): the Vulkan pipeline cache loads v3 packs with the Vulkan backend and installs their SPIR-V and bindings instead of translating (`SpirvShader::LoadPrecompiledBindings`). Identity: the SPIR-V translator version, a hash of the device features and render target setup its output depends on, the manifest flags and the scale. Misses are translated as before (the Vulkan runtime keeps the glslang-builder translator), logged with the hit count, and every translation goes to the shader translation observer, so capturing any Vulkan session (`--shader-capture-dir`) and building with `native-shader-pack.py` produces or extends the pack ([pack contract](native-renderer/SHADER_PACK_FORMAT.md#vulkan-packs)). A capture of `fh1-race-sync` gave 479 shaders; with it `fh1-buy-car` hit 377 and translated only the showroom's new shaders. The race stays at about 30 fps with or without the pack (29 to 32.5), so Vulkan's frame cost lies elsewhere. | M |
| NP-12.7 | **Launcher done, the rest waits on Linux** (2026-09-30): `tools/pinyon.py launch` does what `launch-preview.ps1` does in Python (checks, state directories, mods' database patches, archive members and merges with the build's extractor, the game's environment, hidden runs, render-test scripts, crash reports through `create-crash-report.ps1` on Windows), picks `out/build/<os>-<arch>-<configuration>` and skips shader preparation off Windows, where Vulkan translates at run time; `fh1-free-roam` run through it on Windows exits normally with its three captures. Still to do, needing the Linux toolchain: shell and Python equivalents of setup, toolchain provisioning, SDK preparation, build, shader preparation and launch; artifact keys from the Vulkan device UUID; a CLI or TUI launcher; a documented desktop-build-then-copy-to-Deck workflow and a distrobox recipe for SteamOS. | M |
| NP-12.8 | Deck qualification: gamescope and Wayland presentation, 1280×800, the POSIX multi-object wait polling and `SCHED_FIFO` degradation measured and fixed if pacing regresses, controls layout. | M |

**Gates.** Disc-to-play on Ubuntu 24.04 and on a Deck with the documented
steps; the route matrix runs with zero executor skips on RADV; frame time
within an agreed margin of the Windows 1x baseline on comparable hardware.

## NP-13 macOS

| Item | Work | Size |
| --- | --- | --- |
| NP-13.1 | `mac-arm64` preset, ARM64 baseline, verification of the Mach-O `musttail` thunks for 76,502 functions under the small code model. | S |
| NP-13.2 | Guest-code correctness on ARM64: the render-test routes and save and load flows, hunting simde lane-order, denormal and `vmsum` NaN discrepancies; deterministic routes must match Windows outcomes. | M |
| NP-13.3 | MoltenVK validation of the Vulkan executor (portability subset gaps, sample-rate shading, storage-buffer range, MSAA depth resolve, timeline semaphores); record the Metal-via-MoltenVK baseline. | M |
| NP-13.4 | macOS tooling: Homebrew-pinned toolchain manifest, app bundle layout with dylibs beside the executable. | S–M |
| NP-13.5 | Conditional: a native Metal backend only if NP-13.3 shows unacceptable overhead or an unworkable gap. Not recommended by default. | XL |

## NP-14 Android

| Item | Work | Size |
| --- | --- | --- |
| NP-14.1 | SDK Android build: NDK toolchain, the missing `rex/main_android.h` glue, SDL3 activity and Gradle project, Android surface path. | L |
| NP-14.2 | **Built; AArch64 not run** (SDK `b9a5de0`): on Linux and Android for x86-64 and AArch64, `Fiber` switches with its own assembly routine instead of `ucontext` (Android has no `makecontext`/`swapcontext`; glibc's `swapcontext` made a `sigprocmask` system call per switch): the callee-saved registers and the floating-point control state (MXCSR and the x87 control word, or FPCR and FPSR) go on the fiber's stack and the stack pointers are swapped; a new fiber starts from a prepared frame returning into a thunk that calls its entry. macOS keeps `ucontext` (`REX_FIBER_STACK_SWITCH=0` forces it anywhere). A standalone harness under WSL gcc 13 passes at -O2 and -O0 (resume, 64 fibers by 1,000 rounds matching the same work on the main stack, per-fiber rounding mode, 16-byte alignment with deep recursion, a second thread), and a round trip takes 21 ns against 648 ns with `ucontext`. The AArch64 routine assembles with clang 20 for `aarch64-linux-gnu`; running it waits on ARM64 hardware (NP-14). | S–M |
| NP-14.3 | **Built, untested on a large-page kernel** (SDK `30896db`): the runtime already mapped the `0xE0000000` heap with a 0x1000 host offset when the allocation granularity exceeds 4 KB, but `PhysicalHostOffset` and the generated `REX_PHYS_HOST_OFFSET` hard-coded the offset per platform with none on Linux, so a 16 KiB or 64 KiB kernel would translate every 0xE0 address wrongly. On Linux and Android both now read `rex_physical_host_offset_e0`, which `PhysicalHeap::Initialize` sets from the granularity; Windows and macOS keep their constants (Windows build and frame replays unchanged). The codegen template change applies when the generator is next rebuilt. Running on a 16 KiB kernel waits on NP-12's Linux toolchain and ARM64 hardware | M |
| NP-14.4 | Mobile GPU constraints: descriptor-indexing fallback, BC decode when compression is absent, storage-buffer bucketing, MSAA 2x emulation, Adreno and Mali workarounds. | L |
| NP-14.5 | Cross-build and sideload workflow: codegen and NDK cross-compile on the user's PC from their own ISO, on-device or PC-side pack production keyed by the device features hash, nothing derived distributed. | M |
| NP-14.6 | Performance and thermals on the reference device; touch and controller input; scale fixed at 1x. | L |

## NP-15 Vulkan first

**Why.** Every platform after Windows runs Vulkan, and maintaining two
renderers at the same level costs twice. The executor core is already shared
(NP-9.0), so maturing one backend is mostly the Vulkan layer: its speed, its
shader preparation, the D3D12-only fast paths, and qualification beyond the
one NVIDIA card it has run on.

| Item | Work | Size |
| --- | --- | --- |
| NP-15.1 | **Superseded by the [performance backlog](PERFORMANCE_BACKLOG.md) (2026-09-30), whose target is beyond parity.** Race-frame parity: the Vulkan race frame is about 19.6 ms against 16.7 ms on D3D12, bound by the GPU commands thread, where `UpdateBindings` and the driver's descriptor allocation and writes are the largest share. Move per-draw descriptor work into the recorded stream (push descriptors or dynamic uniform buffers, descriptor buffers where supported), then re-profile. | M–L |
| NP-15.2 | Shader preparation for Vulkan like D3D12's: produce a Vulkan pack for the chosen scales at preparation time and validate it with a compiler-free route (every pipeline from the pack, no translation), keyed by the Vulkan device and driver, so play never stutters on a first-seen shader. | M |
| NP-15.3 | Port the D3D12-only texture-cache fast paths (reflection-cube import, scaled 32-bpp, linear video upload) and anything else the D3D12 executor does natively that Vulkan does through the generic texture cache. | M |
| NP-15.4 | Higher scales on Vulkan: every route at 1x to 4x with no executor skips, and NP-4.10's window and shadow artifacts checked on Vulkan too. | M |
| NP-15.5 | **Superseded, 2026-10-05:** Vulkan is the sole supported graphics API. Schema 28 migrates saved Direct3D 12 selections; launcher and in-game settings no longer offer it. No automatic legacy fallback. | S |
| NP-15.6 | Vendor qualification of the Vulkan path on an AMD and an Intel GPU (see Needs a person). | S (+hardware) |

**Historical gates for the default switch (NP-15.5), superseded by the support policy above.** The race frame within 5% of
D3D12 or better on the baseline machine; every render-test route passing on
Vulkan at 1x to 4x, and the golden frame replays matching D3D12 within
tolerance; a validated Vulkan pack with zero runtime translations on the
route matrix; at least one AMD or Intel GPU qualified; no open Vulkan-only
visual bug.

## NP-X Quality and tooling (ongoing)

- **CI compiles C++.** **Windows done**: `PINYON_SHIFT_HOST_TESTS_ONLY`
  configures without generated game code, and `tools/ci-host-tests.ps1` builds
  `pinyon_shift_host_tests` (the SDK runtime, the UI API, host UI, host config
  and profile-body tests, the shader-pack test and the sample mod) and runs
  the tests that need no game data; the `host-tests` CI job runs it after
  provisioning the pinned toolchain. Locally: all pass. The pass-tracker and
  execution-key tests went with NP-0.5; Linux follows NP-12.1. The job's
  first run on GitHub happens with the next push.
- **Performance gate.** Keep the three-by-three A/B protocol manual on the
  baseline machine until a fixed CI machine exists; publish the baseline
  summary JSON with every train.
- **Hardware qualification.** AMD, Intel and lower-end GPUs (XR-09) and an
  unscripted human drive (XR-08) before every train; these need people and
  hardware the project does not have and are tracked, not scheduled.
- **Determinism guardrails.** Pose baseline, save payload hash and golden
  replays are mandatory for any timing, numerics or resolve change.
- **Docs hygiene.** One focused document per retained contract; run-by-run
  logs under `.local`; `tools/check-markdown-links.py` in CI stays.

## NP-D Distribution and first run (ongoing)

The legal model does not change: nothing derived from the disc ships, the
user builds locally, packs stay local ([legal](LEGAL.md)). What changes is how
long and how Windows-specific that is.

- **First build time.** Cache the SDK and toolchain builds between source
  versions, use a compiler cache for the generated translation units, produce
  packs in parallel with the build, and measure; target under 20 minutes on
  an eight-core machine from the current 20–60.
- **Launcher core.** Extract a Python or CLI core (setup, verify, build,
  launch, report) that the WPF launcher calls today and that NP-12.7 reuses on
  Linux and macOS; a cross-platform GUI is a later option.
- **Signing and portability.** Sign the launcher and preview executables;
  support portable installs (both on the README roadmap).
- **Crash reporting.** Keep the sanitised bundle and prefilled issue; the
  POSIX reporter from NP-12.2 joins it.

## Pending to formalize

Accepted directions that still need research before they become numbered
slices with items, sizes and gates.

### Opt-out crash and log collection

Collect crash reports and short logs from players' machines so bugs seen on
other hardware can be debugged, cheaply or for free to host.

- **Consent.** On by default only if the maintainer decides so after
  reading the privacy implications; a first-run notice, a SETTINGS switch to
  opt out, and nothing sent from a machine that opted out. Payloads never
  hold game files, saves, generated code or memory dumps (the existing crash
  bundle already excludes them) and carry no account or machine identifiers
  beyond a random install ID.
- **Hosting candidates.** Sentry's free tier or a self-hosted GlitchTip
  (Sentry-compatible, one small VM); GitHub issues through the existing
  crash-report link (free, but needs the player's GitHub account); or a
  Cloudflare Worker writing to R2 (free tier covers low volume). Measure the
  bundle size and pick by cost, retention and triage workflow.
- **What to send.** The crash report's signal or exception, stack and module
  list, the build and SDK commits, the GPU and driver, the settings, and the
  last lines of the runtime log.

### Rendering debug views for power users

A DEBUG VIEW setting (hidden behind an advanced toggle) that changes how the
renderer draws, for curious players, modders and bug reports: wireframe,
geometry only (flat shading, no textures), one render target at a time (the
HDR scene, depth, the shadow maps, the reflection cube, bloom), textures'
mip levels in colour, overdraw, and hiding classes of draws (UI, particles,
vegetation). Most of these sit in the executor or the host pipeline state
(fill mode, a replacement pixel shader, which surface the presenter shows),
so they need no guest changes; the draw classes need the census's draw tags
(NP-2.0). Each view is a hot cvar, so frame dumps and routes can use them
too.

### Feature requests

Add a GitHub issue template for feature requests (what, why, where in the
game) next to the crash template, and a short "Request a feature" section in
the README that links to it and says how requests are triaged into this
backlog.

### Modern upscalers (DLSS, FSR 3 and 4) as optional mods

Offer DLSS and FSR 3 or 4 as optional upscalers, alongside the CAS and FSR 1
spatial ones of NP-4.2.

- **Legality first.** Before anything ships, read the current licences: the
  NVIDIA DLSS SDK (and Streamline) terms for integrating and redistributing
  the runtime DLL, and AMD's FidelityFX SDK licence (FSR 3 is MIT; FSR 4's
  terms and its RDNA 4 requirement). If redistribution is not allowed, the
  mod loads a runtime the player supplies. An "injector" into the shipped
  game is never needed: the renderer is ours, so this is a normal
  integration behind a mod or setting.
- **The hard part is the inputs.** Temporal upscalers need per-pixel motion
  vectors, depth and a jittered projection; the title renders none of them.
  Depth is available from the executor's surfaces. Camera motion vectors can
  be reconstructed from depth and the previous and current camera matrices
  (which the guest's constants carry); moving cars and characters would need
  per-object motion or would ghost. Research: find the view and projection
  constants per frame, build camera-only vectors, measure the ghosting on the
  race route, then decide whether per-object vectors are worth it.

### Game internals documentation (after the backlog)

When the numbered slices are done, write a thorough, decomp-style account of
the game's internals in the repository, so others can understand and build on
the title's code without repeating the reverse engineering: the main loop and
threads, the world and session objects, the renderer's command stream and
passes, the save and profile formats, the UI and script systems (functors,
scenes), the video path, and every function, offset and contract the backlog
named (the symbol table is the index). One document per subsystem under
`docs/`, each claim tied to an address or a reproducible route, and the
generated symbol table kept as the single source of names.

### Loading times on modern storage

Make boot, title-to-world, event entry and fast travel as short as a PC on
an SSD or NVMe drive allows, instead of paced for the Xbox 360's DVD and
memory budget.

- **Measure first.** Add load-phase markers (boot to title, title to free
  roam, event entry, event exit, fast travel) to the render-test JSONL and
  the critical-path trace, and record a baseline per phase on
  `fh1-race-sync` and a free-roam route.
- **Known evidence.** Host file I/O is small: an archived run read 189 MB
  in 4,538 reads for 91 ms of total read time, and 1,203 opens took 108 ms
  (`xboxkrnl_io.cpp` reads are synchronous; `HostPathDevice` does one
  `ReadFile` per call). Load time is therefore expected to sit in guest work
  rather than the drive: guest-code asset decompression, texture reloads (a
  single transition frame reloaded 75-350 textures and took 212-343 ms in a
  2026-09-28 play session), shader and pipeline availability, and title
  waits paced by frames or vblank.
- **Candidates once measured.** Unthrottled frame pacing while a loading
  screen is up (NP-3.7's variable-delta work may cover part); parallel or
  asynchronous `NtReadFile`/`NtReadFileScatter` and read-ahead of the
  archives a load touches; caching decompressed archives or assets on disk
  between runs; batching the texture uploads of a load; skipping the
  remaining intro and legal screens by default; and finding any minimum
  loading-screen durations in the title that exist only for disc streaming.
- **Guardrails.** Loads must still produce the same world state (vehicle
  pose baseline, save payload), and nothing may change the AppData save.

### Compile uncached shaders on the fly

A shader missing from the pack drops its draws until the next graphics
preparation: a 2026-09-28 play session hit 12 such shaders, and one of them
failed more than 32,768 draws before the session ended. The misses are
recorded (`cache/fh1-shader-misses`), but they only reach the pack when the
launcher reproduces the whole pack, which it does only when the build
changes.

- **Goal.** Translate and compile a missed shader in the background during
  play, draw it as soon as it is ready (the draw is skipped until then, as
  with a pipeline still being created), and keep the result in a local
  delta cache next to the pack so later sessions and later builds with the
  same translator version reuse it instead of recompiling.
- **Open questions.** NP-0.1 took the translator out of the runtime DLL, so
  on-the-fly translation needs the producer loaded on demand (or a separate
  translator module) rather than re-linking it into `rexgpu-fh1`; the delta
  cache has to be keyed like the pack (translator version, vendor, flags and
  scale) and should fold into NP-9.4's pack format v3; a preparation run
  should merge the delta into the pack and drop it; background compilation
  must not stall the GPU commands thread.
- **Gate idea.** A play session that hits a pack miss renders the missing
  draws within a few frames and logs no repeated `Failed in backend`
  errors, and the next launch loads those shaders from the delta cache
  without a preparation run.
- **Known gap in the preparation route.** On `fh1-race-sync` from the
  `appdata-2026-09-27` seed, 2 of 11 runs on 2026-09-28 missed vertex
  shaders `953C0C0D7A505911/7F` and `DAB93405F7249276/0` while the title
  saved a car card, which fails the route's forbidden-error check. The
  preparation route does not render that thumbnail path; until misses
  compile on the fly, the capture route should reach it (or the seed's
  cards should be in a state that renders them every run).

### Faster graphics preparation

Preparing graphics ("Preparing graphics for 1x") took about ten minutes
on a modern machine, and it ran far more often than it needed to. NP-0.8
made translation parallel, removed the per-file costs and keyed
preparation on the graphics sources: a 1x preparation now takes 4 min 32 s,
almost all of it the two game routes, and only runs when graphics code,
settings, the driver or recorded misses change. The rest of this entry
stays pending.

- **Where the time goes** (a 1x production on 2026-09-28 after NP-0.8, 4.5
  minutes without rebuilding the producer; before it 6.6): shader
  extraction 7 s (was 17-19 s), producer run 2 min 4 s (the disc corpus
  loads in 33 ms and translates in 1.2 s, was 55 s and 1 min 45 s; the
  capture route is the rest), pack build 11 s, strict validation route
  2 min 3 s. A launcher run that also rebuilds the producer takes longer.
- **Done in NP-0.8.** Parallel translation (105 s to 1.15 s), one corpus
  file and one capture file instead of about 37,500 small files, and a
  preparation key on the graphics sources instead of the binaries.
- **Re-preparation after every new pack miss.** Each recorded miss changes
  the key and reruns everything for a handful of shaders; translate only
  the new misses and append them (this meets the on-the-fly compilation
  entry above).
- **The two game routes.** The capture route and the strict validation
  route replay about 9,000 frames each at the game's own pace while hidden.
  Run them unpaced, capture pipelines only when the catalog inputs change,
  and move the strict check to a shorter route or to the background after
  the game starts, keeping it as a gate for release packs.
- **Smaller steps.** Cache the extracted corpus by dump hash (7 s); build
  the pack from the capture in the producer instead of a Python pass
  (11 s); ship a prebuilt producer with releases (NP-D) instead of building
  it locally.
- **Gate idea.** A rebuild that does not touch the translator starts the
  game with no preparation; a first preparation finishes in under two
  minutes on an eight-core machine; packs stay byte-identical to the
  single-threaded producer.

## Parking lot

Ideas considered and not scheduled; add to a slice when a train has room.

- Local rivals and leaderboards from `GameplayLog` and the profile, replacing
  the dead Xbox Live rivals (all Live exports are stubs today).
- Rich presence for Discord and Steam.
- Import cars from *Forza Horizon 2* (README roadmap; needs NP-10 and asset
  format research).
- Accessibility: subtitle size and HUD scale through the UI4 root transform
  once NP-4.4 finds it.
- DualSense adaptive triggers and a Deck controls layout beyond defaults.
- HDR output and a true wider back buffer (recorded under NP-4.8).
- Frame generation: not planned; distinct rendered frames are the contract.
- Low priority: leads from the `NOOBboy786/pinyon-shift` fork (six commits
  by Sagnik Ray, 2026-09-23 to 09-26, on the 2026-08-26 `main`; its `dev`
  has nothing ours lacks). Port by hand, never merge:
  - **XMA hardening** (their patch 0037), missing from ShiftGlue: null
    `TranslateVirtual` and allocated/enabled checks in `Work`, `Clear` and
    `Release` (`Release` returns instead of asserting); free `av_packet_` in
    the destructor and drop the unused 128 KB `av_buffer_alloc` (a leak per
    context); grow `xma_frame_` from `1 + 4096` to 8192 bytes so a maximum
    frame plus FFmpeg's input padding fits (a likely over-read); drop the
    `assert_always` calls in `GetPacketNumber` and treat
    `kPacketOutOfRange` like `kBufferInvalid`, without a warning. Check
    against the XMA stall diagnostics before landing.
  - **AMD and Intel TDR report** (their patch 0038): they report more than
    10 minutes of driving without a TDR on a Ryzen 3 5300U (Vega 6). The
    patch ends the submission after 512 draws, after 32k indices or at any
    draw of 12k or more indices (file-static counters, guessed thresholds),
    and puts a shared-memory UAV barrier before the memexport fast readback on
    AMD and Intel. It is evidence for NP-X hardware qualification, not a fix:
    ask the contributor to test a current build first.
  - **Europe (MS-2506) and Japan (MS-2507) dumps** for
    `config/supported-dumps.json`: each has the USA entry's ISO size,
    extraction counts and XEX hashes, and only the ISO SHA-256 differs.
    Redump does not publish SHA-256, so add them only after an owner of those
    discs verifies the hashes.
  - Skipped: the hard-coded `0.1.1` state-root discovery, VRR and tearing
    forced off, the thread scheduler (overlaps NP-3.1, unmeasured), the
    hitch logger, live settings reload and launcher changes (superseded),
    and the PATH filter that drops every entry containing `&`. The
    `WIN32_LEAN_AND_MEAN` guard is trivial and can be taken any time.

## Mapping to the original asks

| Ask | Slices |
| --- | --- |
| Confirm and remove remaining Xenos compatibility; port the rest to the native renderer | NP-0, NP-9.4, NP-9.5 |
| Optimise the renderer | NP-2, NP-9 |
| Optimise the CPU side for modern machines and multi-threading | NP-3, NP-9.3 |
| Any resolution, aspect ratio, ultrawide, modern graphics settings | NP-4 (settings surface from NP-1) |
| Replace ImGui with native menus, achievements, profile settings | NP-1, NP-5, NP-6 |
| Modding APIs, UI first | NP-7, NP-11, NP-10 |
| Cheat menu for playthroughs | NP-8 |
| Metal and Vulkan for Android and macOS later | NP-9.0, NP-9.4 as prerequisites; NP-12, NP-13, NP-14 |
| Additions | HFR correctness (NP-3.7), save backups and photo export (NP-5.5, NP-5.6), profile isolation for mods (NP-7.5), CI that compiles C++ (NP-X), first-build time (NP-D), parking lot |

## Notes for later

- **Say what FSR 1 does to the resolution.** Make the FSR 1 setting explicit
  for players: show the base resolution the game renders at, then the final
  resolution after the FSR 1 pass (for example, "renders 1280x720, upscaled
  to 1920x1080"), in the launcher's graphics panel and the in-game display
  settings (NP-1, NP-4.2), so nobody has to work it out from the scale
  factor. Also make FSR toggles don't require restart
- **Free-roam frame pacing.** The F3 frame-time graph shows a consistent,
  periodic spike in free roam (not on the race routes). Find the period and
  which thread owns it (streaming, the decoder's waits, texture reloads,
  present) with the perf CSV and the thread sampler on `fh1-free-roam` or
  `fh1-long-drive`, then fix or smooth it.
- **FSR options.** Expose FSR's settings instead of one toggle: the target
  (output) resolution to upscale to, the sharpness, and quality presets that
  pick the render scale for a target, in the launcher and in game (joins the
  FSR 1 resolution note above and the modern-upscalers item).
- **A 1.5x render scale** so the game renders at 1920x1080 (1.5 x 1280x720)
  for 1080p screens without FSR. The draw resolution scale is an integer
  today (1x, 2x, 3x), so this needs fractional scale support through the
  executor's surfaces, resolves and the translator's baked scale.
- **More cheats: destructible scenery.** Cheats that make trees, bushes and
  barriers break away on contact instead of acting as solid walls, next to
  the existing cheat menu (NP-8).
- **DLC support.** Load the game's downloadable content (car packs, tracks)
  from the player's own DLC files: content packages mounted like the disc,
  the title's content enumeration and licence checks answered for them.
