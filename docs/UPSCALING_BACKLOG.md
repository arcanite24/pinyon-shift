# Upscaling and frame generation backlog: DLSS, FSR, XeSS, Lossless Scaling

Created 2026-10-16 at `dev` `b6a18dc1` (ShiftGlue `773539d`). Goal: offer
every upscaler and frame generator a player's hardware can run, in more than
one version where versions differ, as opt-in settings beside today's
bilinear, CAS and FSR 1. The official reference implementations come first;
faster community forks come after them, and only where a measurement on our
devices shows the gain. This backlog takes over FB-14.6 to FB-14.9
([#523](https://github.com/arcanite24/pinyon-shift/issues/523) to
[#526](https://github.com/arcanite24/pinyon-shift/issues/526)) and builds on
DR-5.4's staged research in
[DESKTOP_RENDERER_BACKLOG.md](DESKTOP_RENDERER_BACKLOG.md). The idea
"frame interpolation for high frame rates" is in DR's dropped list; the
maintainer reversed that on 2026-10-11 (NATIVE_PORT_BACKLOG.md), and it is
planned here as an opt-in feature, off by default.

## Where it stands

- **Spatial output scaling ships:** bilinear, CAS and FSR 1 (EASU and RCAS)
  in the presenter (`present_effect`, SDK `src/ui/presenter.cpp`,
  `src/ui/vulkan/vulkan_presenter.cpp`). On the 8 Elite FSR 1 costs 1.4 ms.
- **FSR 2 and 3 run as providers but without the game's inputs.**
  `present_effect=fsr2|fsr3` dispatches FSR 2.3.3 or 3.1.4 (AMD's
  signed runtime on Windows, the same library built from source on
  Linux, Android and macOS, UP-2.1) once per guest frame with the real frame delta (UP-0.3,
  UP-1.1), on a copy of the frame without the HUD, which goes back on
  after the upscale (UP-1.2), with the scene's depth and camera motion
  vectors (UP-1.3, UP-1.4) and a jittered scene (UP-1.5). Cars and other
  moving objects carry their own motion (UP-1.7). Before UP-0.3 it was a dormant path behind
  `REXGLUE_ENABLE_FIDELITYFX` that fed one texture as colour, depth and
  motion, reset every frame and assumed 16.7 ms.
- **The game has no motion vectors, no jitter and no TAA.** Its motion blur
  takes six taps along a camera velocity. Depth exists: the 1280x720
  `24_8_FLOAT` texture is resolved every frame, and DR-2.2 keeps it current.
  The HUD boundary is known (the front buffer's `2_10_10_10_AS_10_10_10_10`
  view), and `scene_post.cpp` already snapshots the pre-HUD scene. The
  camera comes from the scene draws' own matrices (UP-1.3).
- **The renderer is Vulkan-only** on Windows, Linux and the Deck, Android
  and macOS (through MoltenVK). D3D12 is legacy. So every SDK is judged by
  its Vulkan path.
- **The internal resolution is an integer multiple** of 1280x720 (1x to 4x).
  The upscale ratio is therefore output size over 720p times N. Those ratios
  already match the standard modes:

  | Output | 1x | 2x | 3x |
  | --- | --- | --- | --- |
  | 1080p | 1.5 (Quality) | native AA (DLAA, FSR native) | — |
  | 1440p | 2.0 (Performance) | 1.0 (native AA) | — |
  | 2160p | 3.0 (Ultra Performance) | 1.5 (Quality) | 1.0 (native AA) |

  Fractional internal scales (1.33x, 1.7x) need DR-2.1's scale per surface
  and a translator change. They are an open question, not a prerequisite.

## What each option needs, and what we can feed it

| Option | Kind | Inputs | Vulkan | Platforms for us |
| --- | --- | --- | --- | --- |
| FSR 1, CAS, NIS | Spatial | Colour | Shader source | All (FSR 1 and CAS ship) |
| SGSR 1 (Snapdragon) | Spatial | Colour | GLSL source | All, aimed at Android |
| MetalFX spatial | Spatial | Colour | Metal only | macOS (Metal interop) |
| FSR 2.3 / 3.1 upscaler | Temporal | Colour, depth, motion, jitter, reactive mask | Yes (source, or the SDK 1.1 DLL) | All, from source |
| Arm ASR (FSR 2.2 for mobile) | Temporal | Same as FSR 2 | Yes (source) | Android, Deck, all |
| SGSR 2 | Temporal | Colour, depth, motion, jitter | GLSL source | Android, all |
| DLSS SR / DLAA | Temporal (ML) | Colour, depth, motion, jitter, exposure | Yes (NGX) | Windows and Linux, RTX |
| XeSS SR | Temporal (ML) | Colour, depth, motion, jitter | Yes (`xess_vk.h`) | Windows, any SM 6.4 GPU (DP4a) |
| MetalFX temporal | Temporal (ML) | Colour, depth, motion, jitter | Metal only | macOS, M1 and later |
| FSR 4 | Temporal (ML) | As FSR 3.1 | **No official Vulkan path** | Windows, RDNA 3/4, via a D3D12 bridge |
| FSR 3.1 frame generation | Interpolation | HUD-less colour, depth, motion, UI | Yes (SDK 1.1) | All with Vulkan 1.3 |
| DLSS frame generation (2x, MFG) | Interpolation (ML) | As DLSS SR, plus HUD-less colour | Yes, through NGX (`nvsdk_ngx_helpers_dlssg_vk.h`) or Streamline; dynamic MFG and vsync with frame generation are D3D12 only (UP-0.2) | Windows and Linux, RTX 40/50 |
| XeSS frame generation | Interpolation | As XeSS SR | **D3D12 only** | Windows, via a D3D12 bridge |
| MetalFX frame interpolation | Interpolation | Colour, depth, motion | Metal only | macOS 26 |
| Lossless Scaling (LSFG 3.1) | Interpolation, image only | Two finished frames | Yes (lsfg-vk method) | Any Vulkan GPU, needs the player's own `Lossless.dll` |

So the spatial options and LSFG work today. Everything temporal, which
includes every reference implementation the goal names, waits on one shared
piece of work: real inputs (UP-1). That makes UP-1 the critical path. Every
provider after it is mostly glue on top.

## Licensing: we do not ship the binaries, setup fetches them

Pinyon Shift releases ship source and the launcher only. The player's
machine builds the game, and `tools/package-launcher.py` refuses any
`.dll`, `.exe` or `.so`. Third-party projects are already **downloaded
during local setup** from their own release URLs, pinned by version and hash
in `config/release-toolchain.json` and listed in `THIRD_PARTY_NOTICES.md`.
Upscaler runtimes fit that same pattern. They are not redistributed by us;
the player's setup fetches them from the vendor:

| Runtime | Licence (checked 2026-10-16) | How it reaches the player |
| --- | --- | --- |
| FSR 1/2/3.1 source, FidelityFX SDK 1.1.x (Vulkan) | MIT; the signed DLLs may be redistributed in binary form with the notice | Built from source fetched at setup (already wired: `cmake/rexglue_fidelityfx.cmake`). Default on |
| FidelityFX SDK 2.3 (FSR 4, ML frame generation) | AMD signed-DLL licence: binary only, notice kept, no reverse engineering | Setup fetch, D3D12 bridge only. FSR 4's model itself comes with AMD's driver |
| Arm ASR | MIT | Source at setup |
| SGSR 1/2 | BSD-3 | Source at setup |
| NIS | MIT (checked in UP-0.1) | Source at setup |
| XeSS 1.x to 3.x | Intel Simplified Software License: unmodified binaries may be redistributed with the notice | Setup fetch from `github.com/intel/xess`, several pinned versions |
| DLSS SDK (`nvngx_dlss.dll`, `libnvidia-ngx-dlss.so`) | NVIDIA RTX SDK licence: object code only inside an app; the SDK must not be made subject to an open-source licence (4(e)); NVIDIA marks need approval | **Setup fetch, on by default on Windows** from `github.com/NVIDIA/DLSS`, approved by NVIDIA (2026-10-20); the DLL is staged with NVIDIA's licence, and a newer version folder a player adds is used first. No NVIDIA headers or binaries in our repository; names in text only, no logos |
| Streamline (`sl.*.dll`) | MIT source; production builds need NVIDIA-signed plugin DLLs | Not needed: raw NGX covers SR and frame generation on Vulkan, Windows and Linux (UP-0.2) |
| `Lossless.dll` (Lossless Scaling, paid, THS) | Proprietary; no SDK, API or permission statement found | **Never fetched or shipped.** Loaded from the player's own Steam install, found through the Steam library folders, or a path they choose |

Recommendations:

- Ship nothing proprietary in the repository or in releases. Keep the
  current packaging rule.
- FSR from source is the default temporal option, because it runs
  everywhere and has no licence friction.
- DLSS and XeSS are opt-in downloads with the licence shown, plus drop-in
  folders. A drop-in folder is also how players run other versions, the
  way DLSS Swapper users do. The NVIDIA app's preset override keeps working
  on top.
- Before the DLSS download is turned on in a release, ask NVIDIA developer
  relations whether a free, source-only project with a setup-time fetch
  needs anything more (attribution screen, notice). Also ask THS about
  `Lossless.dll` before UP-5's in-engine path ships (UP-0.1). This is a
  reading of the licences, not legal advice.
- The repository's licence is BSD-3, which is permissive, so 4(e) is about
  vendoring NVIDIA's code into our tree, not about linking. We avoid that by
  fetching at build time.

## Decision

- Providers sit behind one interface in the SDK presenter. Each provider
  declares its inputs, the platforms and GPUs it supports, and its version.
  The presenter feeds them all from the same input set (UP-1). A version is
  data, not code, wherever the SDK keeps a stable ABI: DLSS, XeSS and the
  FidelityFX DLLs are loaded from versioned folders,
  `upscalers/<provider>/<version>/`, filled by setup or by the player.
- Order: inputs, then the reference temporal providers (FSR 3.1 from source,
  DLSS, XeSS), then the spatial and mobile ones, then frame generation, then
  forks, then the D3D12 bridge for FSR 4 and XeSS frame generation. LSFG
  runs in parallel from the start, because it needs no inputs.
- Upscaling happens at present time first. The HUD is drawn to its own
  surface and composited after the upscale. The game's motion blur and
  depth of field go off while a temporal provider is on (DR-5.4 stage 3).
  Placing the upscale before post-processing waits for DR-2.1.
- Frame generation is off by default and only offered with a latency aid
  where one exists: Reflex through `VK_NV_low_latency2`, Anti-Lag 2 through
  `VK_AMD_anti_lag`, or our own frame limiter otherwise.
- Generated frames are host frames only. The simulation-step and title-frame
  pairing (`ee41d07e`, `38a127f9`) stays as it is; generated frames never
  count as title frames.

## Verification rules

- Goldens stay bit-exact with every provider off.
- Every provider is checked on a pinned seed route (`run-fh1-render-test.py`)
  for these: MAE against native 3x on the whole frame, on the car and on the
  HUD; a paused-frame test that expects zero vectors and a static image; and
  a ghosting capture of an overtaking car and of the pre-race camera sweep.
- Cost is measured per device as the GPU time of the provider's own
  dispatch, with in-run A/Bs (toggled inside one route) on the RTX 4080, the
  Deck, the Odin or Astra (8 Elite) and the Mac mini. A single run never
  settles a cost.
- Frame generation is measured by present spacing, the input-to-photon
  proxy (latency marker deltas), and the maintainer's own look at 120 Hz with
  and without VRR.
- A fork is adopted only if it beats the reference on the same device in an
  in-run A/B and its quality metrics stay within the reference's run noise.
  The fork's own claims do not count.

## Items

### UP-0 Groundwork

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| UP-0.1 | **Licence and permission check**: confirm the NIS licence; read the DLSS programming guide on DLL signature checks and on loading a DLL from another folder; ask NVIDIA about a setup-time fetch for a free project; ask THS about loading `Lossless.dll`; record the answers in `docs/LEGAL.md` and `THIRD_PARTY_NOTICES.md` | Written policy before anything is downloaded | S | **Policy written, letters pending** (see Progress) |
| UP-0.2 | **Vulkan capability matrix from the SDKs themselves**: does DLSS frame generation run on Vulkan through Streamline 2.14 or raw NGX, and on Linux? Confirm the FSR 3.1 Vulkan DLL names and the XeSS Vulkan feature set by building each sample on multivac and on the Deck | Replaces the "unconfirmed" cells above | S-M | **Done on multivac; Deck extensions checked** (see Progress) |
| UP-0.3 | **Provider interface in the SDK presenter**: query (supported, versions, modes), create and destroy on resize, dispatch with an input set, and the HUD composite after it. Today's bilinear, CAS and FSR 1 move behind it unchanged (goldens bit-exact) | One path for every option | M | **Done**, the HUD composite with UP-1.2 (see Progress) |
| UP-0.4 | **Runtime fetch in setup**: `release-toolchain.json` entries per provider version (URL, SHA-256, licence id), an opt-in licence screen in both launchers, `upscalers/<provider>/<version>/` beside the install, a drop-in folder, and an install check that verifies signatures where the vendor signs | Players get DLSS/XeSS without us shipping them | M | Partly done: DLSS and the Windows FidelityFX runtime are fetched by the build, pinned by commit and SHA-256 in ShiftGlue's CMake (2026-10-20); XeSS and a licence screen open |

### UP-1 Inputs (DR-5.4 stages 0-3)

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| UP-1.1 | **Honest dispatch**: real frame delta, reset only on cuts and resizes, SDR flags on SDR input, and the dispatch cost measured with dummy inputs (DR-5.4 stage 0) | The cost floor per device | S | **Done on multivac** (see Progress) |
| UP-1.2 | **HUD on its own surface**: redirect the HUD's draws to a surface composited after the upscale, which gives HUD-less colour for the upscaler and for frame generation | A sharp HUD at any scale; required by every frame generator | M | **Done on multivac** with a HUD-less copy and a mask instead of a redirect; the HUD itself stays at the game's resolution (see Progress) |
| UP-1.3 | **Depth and camera**: the `24_8_FLOAT` depth (host value halved) and a per-frame view-projection snapshot, from the constants that change every frame or a hook in the camera code NP-4.4 found. Record the addresses in `site/findings` | Inputs for camera vectors | M | Done |
| UP-1.4 | **Camera motion vectors** from depth and the current and previous view-projection, in a compute pass | Correct vectors for the static world | M | Done |
| UP-1.5 | **Jitter** through the `ndc_offset` system constants, on scene-surface draws only, with MSAA forced off while a temporal provider is on | Sub-pixel detail; required by every temporal provider | M | Done |
| UP-1.6 | **Reactive and transparency masks; motion blur and depth of field off** while a temporal provider is on | Less ghosting on particles, glass and UI-like effects | M | Partly done: blur and DOF off; masks deferred to UP-1.7 |
| UP-1.7 | **Per-object vectors decision**: measure ghosting on cars from captures; if it is visible, per-object vectors from the previous frame's guest vertex positions (needs DR-3.1/DR-4.1 identity) | Clean cars, or an accepted limit | L (decision S) | Done: object slot image and per-slot reprojection |
| UP-1.8 | **Exposure input**: the game's auto-exposure value for DLSS and FSR, or auto-exposure in the provider | Stable brightness through tunnels | S | Open |

### UP-2 Reference temporal upscalers

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| UP-2.1 | **FSR 3.1 upscaler from source** (FidelityFX SDK 1.1.x Vulkan backend), plus FSR 2.3 as a second version, with Native AA, Quality, Balanced, Performance and Ultra Performance mapped to the integer scales | The default temporal option on every platform | M after UP-1 | Mostly done: FSR 2 and 3 run on Linux, Android and macOS from source; Native AA and the named modes are open |
| UP-2.2 | **DLSS SR and DLAA through NGX on Vulkan**, on Windows and Linux, with a preset selector (K, L, M and Auto, plus "driver decides" so the NVIDIA app's override wins), several DLL versions from `upscalers/dlss/<version>/` | Best image on RTX | M after UP-1, UP-0.4 | Partly done: Windows, on by default with the DLL fetched at setup; Linux and a preset row open |
| UP-2.3 | **XeSS SR through `xess_vk.h`**, versions 1.3, 2.x and 3.x side by side (each DLL behind the same loader) | An ML option on Intel and on AMD/NVIDIA via DP4a | M after UP-1, UP-0.4 | Open |
| UP-2.4 | **MetalFX temporal on macOS** through `VK_EXT_metal_objects` (export the MTLTextures and the command queue from MoltenVK, encode MetalFX, return through a shared event) | An ML option on Apple silicon | M-L after UP-1 | Open |

### UP-3 Spatial and mobile options

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| UP-3.1 | **SGSR 1 and NIS** as spatial options beside FSR 1 and CAS | Cheaper spatial scaling on Adreno; more choice | S | Open |
| UP-3.2 | **Arm ASR** (balanced and performance presets) and **SGSR 2** (2-pass and 3-pass compute, 2-pass fragment) as temporal options aimed at the 8 Elite and the Deck | A temporal option that fits a mobile frame (target ≤ 1.5 ms at 720p→1080p on the 8 Elite, which is about the cost of FSR 1 there today) | M after UP-1 | Open |
| UP-3.3 | **MetalFX spatial** on macOS (shares UP-2.4's interop) | Apple's spatial scaler | S after UP-2.4 | Open |

### UP-4 Frame generation

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| UP-4.1 | **FSR 3.1 frame generation** on Vulkan (the SDK 1.1 frame interpolation and its swapchain replacement or our own pacing), with the UI (HUD, F6 menu, overlays) drawn on every displayed frame | 60 → 120 on any Vulkan 1.3 GPU, including the Deck | M-L after UP-1.2-1.6 | Open |
| UP-4.2 | **Latency aids**: Reflex markers through `VK_NV_low_latency2`, Anti-Lag 2 through `VK_AMD_anti_lag`, and a frame limiter tied to generated frames otherwise | Frame generation that does not feel worse than without it | M | Open |
| UP-4.3 | **DLSS frame generation and MFG** (RTX 40/50) on Vulkan, through Streamline or NGX depending on UP-0.2 | 2x to 4x on RTX | M-L after UP-4.1, UP-0.2 | Open |
| UP-4.4 | **MetalFX frame interpolation** on macOS 26 | 60 → 120 on the Mac mini | M after UP-2.4 | Open |
| UP-4.5 | **Present and pacing integration**: generated frames carry present IDs, never touch the step gate or the title's flip counters, VRR caps and vsync modes with frame generation on, and the cut and pause detection resets | No pacing regressions with it off; even spacing with it on | M | Open |

### UP-5 Lossless Scaling (LSFG) from the player's own `Lossless.dll`

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| UP-5.1 | **Works with the app today**: check that Lossless Scaling over the borderless window on Windows, and the player's own lsfg-vk layer on Linux and the Deck, frame-generate the game correctly; document the steps and our recommended settings (frame limit at half the refresh, vsync, HUD caveat) on the troubleshooting and playing pages | Players can use LSFG now with no code from us | S | **Done on the Deck; Windows partly verified; documented** (see Progress) |
| UP-5.2 | **In-engine LSFG**: find `Lossless.dll` in the Steam library folders (or a path the player picks), load its compute shaders at runtime into our Vulkan device, using the method lsfg-vk documented: translate the DX11 shaders to SPIR-V; nothing extracted is cached outside the player's machine or committed. Implemented by us from the published method. lsfg-vk's code since its licence change is CC BY-NC-ND and is not reused; its earlier MIT commits may be used with notice | LSFG with a HUD-less input and the HUD drawn on every frame, our pacing, on Windows, Linux, the Deck and Android | M-L after UP-0.1 (THS's answer) | Open |
| UP-5.3 | **LSFG versions and modes**: LSFG 2 and 3.1, multiplier 2x to 4x, flow scale, performance mode; an FP16 path where the GPU has double-rate FP16 (lsfg-vk's v2 test build reports 2-3x faster and 30 % of the memory) | Selectable like the other providers | M after UP-5.2 | Open |
| UP-5.4 | **Android**: LSFG on the Odin, Astra and Fold6 (Adreno 6xx and newer per GameNative's port), with the DLL copied by the player from their own PC install | Frame generation on Snapdragon | M after UP-5.2 | Open |

### UP-6 Optimized forks (after the references exist)

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| UP-6.1 | **Bake-off harness**: one route, every provider and version, GPU dispatch time and the quality metrics, per device, written to a table the site can show | A fair ranking; a fork earns its slot | M after UP-2 | Open |
| UP-6.2 | **Candidates**: Arm ASR against FSR 2.2 (the first real "optimized fork", from Arm); FSR 2/3's own FP16 permutations forced on; SGSR 2 variants (the Unity "optimized" fork claims 4x on Adreno 610; to be re-measured, not trusted); `Snowapril/fsr3-android` and `ychwch/FidelityFX-SDK-Linux` for FSR 3 on arm64 and Linux; image-only frame generation from FSR 3 optical flow (`Swordpdf/ps5-framegen`, GPL-3.0, so a reference only) | Faster options where measured | M each | Open |
| UP-6.3 | **Our own variants** where the bake-off shows a hot pass: half-resolution vectors, fewer RCAS passes, the FSR 1 sharpening shared with a temporal provider | Device-specific cuts | S-M each | Open |

The search for "forks that run way better" found few with evidence: Arm
ASR is the only established one. Most others are small (0-21 stars),
engine-specific (Unity) or unmeasured. Several popular projects are
injectors (OptiScaler, dlssg-to-fsr3). They exist to add upscalers to games
that lack them, which we do not need, since the renderer is ours. UP-6.1
exists so that claims become numbers before anything is adopted.

### UP-7 D3D12 bridge for D3D12-only SDKs

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| UP-7.1 | **Vulkan to D3D12 interop**: a D3D12 device on the same adapter, shared images and timeline semaphores (`VK_KHR_external_memory_win32`, `VK_KHR_external_semaphore_win32`), measured cost per frame | A way to run D3D12-only SDKs from our Vulkan renderer on Windows | M-L | Open |
| UP-7.2 | **FSR 4** (FidelityFX SDK 2.3, ML upscaler 4.1 and ML frame generation) through the bridge, on RDNA 4 and on RDNA 3 since SDK 2.3. Never the leaked or INT8 community builds | AMD's best image on Radeon | M after UP-7.1 | Open |
| UP-7.3 | **XeSS frame generation and XeLL** through the bridge | Frame generation on Intel Arc | M after UP-7.1 | Open |

### UP-8 Player settings and docs

| ID | Item | Expected | Effort | Status |
| --- | --- | --- | --- | --- |
| UP-8.1 | **One "Upscaler" setting** in F6, both launchers and `pinyon_config.py`: provider, version, mode or preset, sharpness; only options the GPU supports are listed, with the reason for any missing one ("needs an RTX GPU", "download DLSS in the launcher", "no Lossless.dll found") | One place for every option | M | Partly done: FSR 2 and FSR 3 in F6, launchers and tools; versions, modes and vendor reasons wait for UP-2.2 |
| UP-8.2 | **"Frame generation" setting**: provider, multiplier, latency aid, warnings when the base frame rate is below 50 | Clear opt-in | S-M | Open |
| UP-8.3 | **Presets** per device class (desktop RTX, desktop AMD, Deck, 8 Elite, Mac) chosen from UP-6.1's numbers | Sensible defaults | S | Open |
| UP-8.4 | **Site**: features.toml, playing, troubleshooting, renderer (input pipeline), a measured table per device, and lessons.md for what did not pay off | Docs match `dev` | S per change | Open |

## Working order

1. UP-0.1, UP-0.2 and UP-5.1 (cheap; they settle policy and give LSFG to
   players now).
2. UP-0.3, then UP-1.1 to UP-1.6 (the critical path), with UP-0.4 in
   parallel.
3. UP-2.1 (FSR 3.1 from source, which proves the inputs), then UP-2.2 and
   UP-2.3, then UP-2.4.
4. UP-3, UP-4.1 with UP-4.2 and UP-4.5, then UP-4.3 and UP-4.4.
5. UP-5.2 to UP-5.4 once THS has answered, in parallel with UP-3 and UP-4.
6. UP-6, then UP-7, then UP-1.7 if the car ghosting calls for it.
7. UP-8 grows with each provider; it is not a final step.

## Not to build

- **Anything that ships proprietary binaries** in the repository or in
  releases, or extracted Lossless Scaling shaders.
- **OptiScaler-style injection or DLL spoofing**: we own the renderer, so
  each SDK is called directly.
- **Leaked or unapproved FSR 4 builds (INT8 on RDNA 2/3)**, and installs
  that disable NVIDIA signature checks (dlssg-to-fsr3's method).
- **D3D12 backend work** to reach D3D12-only SDKs. UP-7's bridge leaves the
  renderer on Vulkan.
- **Fractional internal resolution as a prerequisite**: the integer scales
  already map onto the standard modes (table above).

## Risks and open questions

| Risk | Settled by |
| --- | --- |
| Camera vectors miss transforms that do not go through the camera matrices (scaling the GPU camera matrices failed for this reason, `site/findings/rendering.toml`) | UP-1.3/1.4 on captures, then UP-1.7 |
| Ghosting on cars without per-object vectors | Done in UP-1.7 (object slots) |
| Jitter through `ndc_offset` shakes the HUD, shadows or post passes | UP-1.5 restricts it to scene-surface draws; pixel tests on the HUD and shadow map |
| DLSS frame generation may be D3D12-only through Streamline | Settled by UP-0.2: NGX runs it on Vulkan (available on the RTX 4080, driver 581.08); only dynamic MFG and vsync with frame generation are D3D12-only in Streamline |
| The NVIDIA licence asks for more than a setup fetch allows (marks, notice to NVIDIA) | UP-0.1; the drop-in folder works either way |
| THS objects to loading `Lossless.dll` | UP-0.1; UP-5.1 (the app over our window) needs no permission |
| Frame generation breaks the step gate, flip counters or VRR pacing | UP-4.5, with goldens and pacing A/Bs with it off |
| MoltenVK cannot hand out the Metal objects MetalFX needs | UP-2.4's first step; otherwise macOS keeps FSR from source |
| The present-time placement loses detail that post-processing destroys | Measured in UP-2.1; pre-post placement after DR-2.1 |

## Progress

| Item | Status | Evidence |
| --- | --- | --- |
| UP-2.2 DLSS in player builds | Done on multivac (2026-10-20) | NVIDIA approved shipping DLSS. ShiftGlue's `REXGLUE_DLSS_PROVIDER` (renamed from `REXGLUE_DLSS` so build folders configured before do not keep its old OFF) is on by default on 64-bit Windows: configure downloads the NGX headers, static loader, `nvngx_dlss.dll` 310.9.16 and NVIDIA's `LICENSE.txt` from the pinned `NVIDIA/DLSS` commit, checks each by SHA-256, and the game target stages the DLL and licence in `upscalers/dlss/310.9.16/`. A failed download leaves DLSS out with a warning instead of stopping the configure. The pinned header hashes had been taken from a CRLF checkout, so the download path had never matched; they are now the raw files' hashes, and a local `REXGLUE_DLSS_SDK_DIR` checkout is compared with its line endings normalised. The Windows FSR 2/3 runtime, which setup never fetched, is AMD's signed `amd_fidelityfx_vk.dll` from `PrebuiltSignedDLL/` of the same pinned FidelityFX fork commit, checked by SHA-256 and staged in `upscalers/fidelityfx/1.1.4/` with the SDK's MIT licence; it is the DLL the earlier Windows measurements used. Check: a clean configure in an empty build folder fetched and staged all four files with the pinned hashes; the v4 build with its hand-placed DLLs removed staged them again, and a route on the RTX 4080 logged DLSS 310.9.16, FSR 3.1.4 and FSR 2.3.3 available, created the DLSS feature for 2560x1440 to 3840x2160, and F6 read "DLSS UPSCALES TO 3840X2160" |
| UP-1.7 spikes | Partly done on multivac (2026-10-17) | The maintainer's 28-minute session after the slot variant fix (RTX 4080, 2x, DLSS, 120 fps limit, VSync) still had 63 frames where the title waited 30-440 ms on the GPU fence (6.2 s in all) and 29 frames of 100-230 ms on the title thread. Three causes, each found with the new diagnostics (`pinyon_shift_hitch_sample_ms` and `pinyon_shift_hitch_sample_threads`, which sample the title and named threads' stacks during a long frame on Windows; `pinyon_shift_sql_profile`; ShiftGlue's `gpu_log_long_wait_reg_mem_ms` and `vulkan_log_pipeline_waits_ms`). **Pipelines one at a time:** the fence waits matched new pipelines minute by minute. Each took 3-4 ms to build, but a draw waited for its own before the recorder reached the next draw and asked for the next one, so a scene with 20 new pipelines held the frame for their sum. ShiftGlue `79d3e6f` records such a draw with a pending bind and lets the submission replay wait (`vulkan_async_pipeline_bind_on_replay`, off on Android): the frame's pipelines build in parallel and the longest replay wait seen was 5.7 ms. Drive route with no stored pipelines and the maintainer's GPU settings, 3 runs before and 2 after, leaving out the route's two captures: fence waits 1,167-1,366 to 523-527 ms, frames over 100 ms 6-7 to 2, worst frame 305-416 to 145-166 ms; the warm route did not change; Vulkan validation clean. **Restrictions_Data_Car:** after each race v4 reads every restricted car through that view, and SQLite 3.6.19 rescans its three subqueries for each car: 158-186 ms of one title frame. Four indexes and the same view written with plain joins (`pinyon_shift_game_db_indexes`, on) cut it to 49-55 ms; the rows are identical (game-content findings). **Route captures:** the drive route's two captures cost 175-210 ms each (the frame read back); players never see them, so spike counts leave out the last 4 s. Still open: 50-60 ms title frames for about 2 s after each return to free roam, where the asset worker (v4 `82F0CF00`) and the job workers are busy and the GPU threads idle, the rest of the 49-55 ms database frame, and about 170 ms frames with the title idle in menus, not yet reproduced on a route. |
| UP-2.1 groundwork | Superseded by the row below (2026-10-17) | The provider already loads `amd_fidelityfx_vk.dll` / `libamd_fidelityfx_vk.so` at run time, so FSR from source means building that library from FidelityFX SDK 1.1.4 (MIT) for each platform and staging it beside the game; the SDK 2.x kits are DX12-only and have no Vulkan path. ShiftGlue's `cmake/rexglue_fidelityfx.cmake` (off, `REXGLUE_ENABLE_FIDELITYFX`) builds `amd_fidelityfx_vk` from upstream ReXGlue's fork (`rexglue/FidelityFX-SDK` `eee08db`, "Linux fix") with only FSR 2 and the FSR 3 upscaler. The blocker for Linux, Android and macOS: neither the fork nor AMD's tree ships the Vulkan shader permutation headers, and the SDK generates them only on Windows with `FidelityFX_SC.exe` (`FFX_API_AUTO_COMPILE_SHADERS` is off elsewhere). Next: generate the permutations on Windows, fetch them at setup as a pinned artifact with its hash, and build the library for x64 Linux, arm64 Android and macOS against them |
| UP-2.1 FSR from source | Done on the Deck, Odin 2 Portal and M4 Pro (2026-10-17) | ShiftGlue's `thirdparty/fidelityfx-vk` is a separate CMake project that builds `amd_fidelityfx_vk` (FSR 2.3.3 and the FSR 3.1.4 upscaler, no frame generation) from `rexglue/FidelityFX-SDK` `eee08db`. The Vulkan shader permutations were generated once on Windows with the SDK's own compiler and are checked in as `vk-permutations.tar.gz` (452 headers, checked by SHA-256); a configure-time patch makes the SDK use them instead of running `FidelityFX_SC.exe`. Two backend faults only showed off Windows and are patched at configure time: the per-effect context is declared `alignas(32)` but placed at 4-byte granularity, which MSVC never relies on and clang does (aligned SSE stores crashed context creation on the Deck); and device-local requests skip host-visible memory types, so on unified memory (Adreno, Apple), where every device-local type is host-visible, no type qualified and context creation returned `FFX_ERROR_BACKEND_API_ERROR`. A third fix is ours: depth went in as a `DEPTHTARGET`, which FFX views as `D32_SFLOAT`, but our depth is an `R32_SFLOAT` colour image, and Metal (MoltenVK) asserts on that view; it is now read-only. Linux and macOS game builds build the project as an ExternalProject and stage the library in `upscalers/fidelityfx/1.1.4/` (`REXGLUE_FIDELITYFX_RUNTIME`, on); the Android build compiles it with the NDK and packs it into the APK; the Deck install syncs it. Static scene, last 1500 frames, 1280x720 rendered to 1920x1080 output: **Odin 2 Portal** (Adreno 740, Turnip, its own 1080p screen) FSR 1 16.67 ms median and 0.2 % of frames over 20 ms; FSR 2 17.7 ms, 12.5 % over 20 ms, upscale 4.7 ms of GPU time; FSR 3 18.6-19.2 ms, 18-26 % over 20 ms, upscale 5.8 ms. **Steam Deck** (launched through Steam, headless gamescope at 1920x1080 as when docked): FSR 1 16.7-17.0 ms; FSR 2 26.1 ms; FSR 3 26.9-28.3 ms, upscale 10-14 ms, so neither is usable docked at 1080p. On the Deck's own 1280x800 screen at 1x the output is no larger than the render, and the temporal path does not run. **M4 Pro** (1920x1080 window, 3840x2160 drawable): FSR 3 11.2 ms median against FSR 1's 8.4 ms, upscale 5.0 ms. Captures on all three look right. Windows keeps AMD's signed runtime; its static-scene PSNR against native 3x did not drop with the read-only depth (26.8/28.0/25.3 dB, against 25.4/27.2/24.1 dB with `DEPTHTARGET` on the same build; run-to-run spread was about 1 dB that day). Open: Native AA and the named quality modes |
| UP-1.7 object motion | Done on multivac (2026-10-17) | Each object's own reprojection lands per pixel through an object slot image, not a fifth attachment: scene draws that test and write the scene's depth get a pixel shader variant (`Modification::pixel.object_slot_output`, host render targets only) that atomically maxes `(depth << 8) \| slot` into a full-frame `R32_UINT` storage image at binding 3 of the shared memory set, so the nearest fragment wins in any draw order and across predicated tile bands (the band's row offset is a system constant). Slots come from the executor at draw time: each object's (vertex shader, first vertex buffer, order among that mesh's draws) previous matrix times the inverse of its current one, deduplicated at 1/4096 of clip space so the static world shares one slot (95-145 of 255 slots used on the drive). The swap's camera pass reads the slot at the mirrored pixel and uses that slot's matrix from a per-frame table where the slot's depth equals the depth copy (scaled like it: `D24FS8` depth is kept halved), the camera's elsewhere, then clears the image. The world reads its matrix at `c128`-`c131`, but cars read their own at `c0`-`c3` and draw to another colour target with alpha blending, so the slot test is "writes the scene depth", not the scene colour or opaque blend (`site/findings/rendering.toml`). The same finding showed cars were never jittered (GetSceneJitter checked the scene colour target); they are now, which alone removes the stair-stepped car edges under FSR 3. Base shaders translate byte-identically (the slot constants are declared only in the variant), so the Android shader overrides and the packs still match; the variants are translated at run time on first use. Result on the drive route (RTX 4080, FSR 3.1.4, 1280x720 to 3840x2160): in `present_upscaler_view=motion` the player's car is still in the chase camera instead of carrying the camera's motion, other cars move on their own, and the car's edges no longer stair-step. Still scene PSNR against native 3x: FSR 3 27.3, 28.8, 25.7 dB with it, 27.2, 28.6, 25.6 without; DLSS within its own run-to-run spread (about 0.7 dB on this scene). Median frame rate unchanged (113.1 vs 112.6 fps uncapped); a cold pipeline cache adds first-use pipeline builds for the variants (1 % low 31 vs 44 fps on a fresh route state). Fixed 2026-10-17 (ShiftGlue 8eda23f): even with the player's cache warm the variant pipelines were new, and a draw waited up to `vulkan_async_pipeline_wait_ms` (250 ms on desktop) for each, so DLSS stalled frames by 60-1100 ms driving into new areas on multivac; a scene draw now binds the base pipeline (camera motion) until its variant is built. Drive route from a warm-cache v4 seed, DLSS, GPU-fence waits over 20 ms: 535 and 536 ms in total, worst frame 151 and 153 ms before; 361 and 342 ms, worst 93 and 78 ms after, against FSR 1's 267 ms and 81 ms. Left: a few interior draws seen through the rear window keep the camera's motion (they do not write depth), and reactive masks. `present_upscaler_object_motion=false` turns it off; `present_upscaler_object_debug=1` shows the slots in the motion view |
| UP-1.7 object motion, design | Superseded by the row above (2026-10-16) | What exists: the camera tracking already keys each scene draw's object (vertex shader hash and first vertex buffer) and matches it to the previous frame's matrix, dropping objects drawn with two matrices, so an object's own `previous WVP x current WVP^-1` is known at draw time. What is missing is where it lands per pixel. Plan: for scene draws (camera-matrix draws into the scene colour and depth keys), the translated vertex shader also outputs the clip position transformed by a per-draw `previous_from_current` matrix (identity, or the camera's, for objects without a match), and the pixel shader writes `previous - current` in render pixels to an extra RG16F attachment bound only in the scene pass; the swap camera pass then takes that vector where it was written and the camera reprojection elsewhere. Cost centres: an output and a varying in the SPIR-V translator, the scene render pass and framebuffer gaining the attachment (and the band copies at each resolve, like depth), per-draw constant uploads, and rebuilding the prebuilt FH1 shader packs. Masks (UP-1.6) can share the attachment's spare channels. Not started in this pass because it touches every scene shader and the packs; it gets its own change |
| UP-2.2 DLSS | Partly done on multivac (2026-10-16) | ShiftGlue builds a DLSS Super Resolution provider through NGX on Vulkan when configured with `REXGLUE_DLSS=ON`: CMake downloads NVIDIA's NGX headers and static loader from the pinned `NVIDIA/DLSS` 310.9.16 commit by SHA-256 (or uses `REXGLUE_DLSS_SDK_DIR`), so nothing of the SDK is committed, and release builds leave it out (docs/LEGAL.md: off in releases until NVIDIA answers UP-0.1). NGX loads `nvngx_dlss.dll` from `upscalers/dlss/<version>/` beside the game, newest version first, or from `present_dlss_runtime`; the player supplies it. Instance and device creation enable the extensions NGX reports for the feature (on NVIDIA only). The provider is initialised with a project id and the custom engine type, takes the same depth, camera motion and jitter as FSR, picks the quality mode from the render-to-output ratio (DLAA at 1:1), and `present_dlss_preset` hints J, K, L or M for every mode, default leaving it to the DLSS runtime and the NVIDIA app's override. Jitter sign: DLSS uses FSR's convention; each of the three other signs lost 1.4 to 2.2 dB. Still scene, 1280x720 to 3840x2160 on an RTX 4080, PSNR against native 3x on three static regions: DLSS 310.9.16 27.6, 29.2, 25.7 dB; FSR 3.1.4 27.2, 28.6, 25.6; bilinear 21.6, 22.6, 20.7. F6, both launchers and the config tools list DLSS when it loaded, with the reason when not ("needs an NVIDIA RTX GPU", "no nvngx_dlss.dll in upscalers/dlss"). Left: the Linux loader (`libnvsdk_ngx.a`, `libnvidia-ngx-dlss.so`), the opt-in setup fetch and licence screen (UP-0.4), a preset row in F6, and DLSS frame generation |
| UP-8.1 upscaler setting | Partly done (2026-10-16) | F6 DISPLAY > OUTPUT SCALING lists BILINEAR, CAS, FSR 1 and every temporal provider whose runtime loaded (FSR 2, FSR 3 on multivac with the FidelityFX runtime, and on Linux, Android and macOS from the library the build ships), in version order; a provider that is saved but did not load stays listed as "(UNAVAILABLE)" so the player sees why the game fell back to FSR 1. A new SHARPENING row (OFF to MAX) sets `present_fsr_sharpness_reduction`, used by FSR 1's RCAS and by the temporal providers. The note under the page names the upscaler ("FSR 2 UPSCALES TO"). Both launchers and `pinyon_config.py --output-scaling` / `set-graphics-experiment.ps1` accept `fsr2` and `fsr3`. Checked on multivac in the live F6 menu. Left: a version or quality-mode choice and the vendor reasons ("needs an RTX GPU") come with the second vendor, UP-2.2 |
| UP-1.6 blur, depth of field and masks | Partly done (2026-10-16) | Motion blur and depth of field are off by default already (`disable_motion_blur`, `disable_depth_of_field`); now they stay off while a temporal upscaler is fed, even when the player turns them on. The presenter publishes `rex::ui::IsTemporalUpscalerActive()` each paint and the game's two hooks check it. Checked on the drive route with both effects turned on: the guest frame under FSR 3 has no blur, the bilinear one does. Reactive and transparency masks are not built. FSR's generated reactive mask needs the frame before transparent draws in the same display-referred colour as the input, and the game's opaque scene is in its 7e3 float scene colour before the tone map and post passes, so the two cannot be compared; a mask drawn per transparent draw needs a second target or a second draw for each blended scene draw. The drive captures show no particle or glass ghosting worth that; what ghosts is moving cars, which is UP-1.7's object motion. The masks are decided together with UP-1.7 |
| UP-1.5 jitter | Done on multivac (2026-10-16) | The presenter asks for a Halton(2, 3) sequence of `ceil(8 x ratio^2)` samples (8 per output pixel, 72 at 3x), and the executor adds that frame's sub-pixel offset to the viewport's `ndc_offset` (2 / extent per host pixel) on draws into the scene's colour and depth surfaces only, those most of the previous frame's matrix draws used, so shadows, post passes and the HUD stay still. The offset travels with the frame to the provider. The camera reprojection comes from the game's matrices, which never include it. Sign: the scene is drawn turned 180 degrees, and of the four signs the provider's jitter = minus the surface offset on both axes came closest to a native 3x render of a still scene (PSNR on three static regions, FSR 3.1.4 at 1280x720 to 3840x2160: 19.8, 21.8, 25.6 dB without jitter, 23.4, 27.1, 27.9 with it; the other signs lost up to 0.8 dB on the first two regions and tied on the third). MSAA needed nothing: `fh1_msaa_single_sample` already keeps the 4x surfaces single-sampled by default; a player who turns MSAA back on gets jitter on top of it. `present_upscaler_jitter=false` turns it off. Fix after the maintainer's play test (2x, 4x MSAA, FXAA): flickering neon columns at the left and right edges, low on the screen. A screen-space pass inside the scene surface ends exactly at the screen edge, so moving it by the jitter left a half-pixel column unwritten each frame, and FXAA spread the stale colours a few pixels in. Only draws whose vertex shader reads the camera matrix are jittered now; the edges were clean over six consecutive frames, and the still-scene PSNR rose slightly (23.6, 27.6, 28.0 dB) |
| UP-1.3 and UP-1.4 depth and camera motion | Done on multivac (2026-10-16) | No hook was needed: scene vertex shaders read each object's world-view-projection from `c128`-`c131`, and the static world shares one matrix, so the executor groups the frame's depth-tested draws by matrix, takes the largest group as the world, and matches its objects (vertex shader and first vertex buffer) with the previous frame's. The previous matrix times the inverse of the current one is the camera's reprojection for static geometry; a frame with no matching object, or a change past 0.25 in any element, is a cut and resets the history. The lens comes from the same matrix (48.5 degrees, near 0.3, far about 20,000 in free roam). Depth is copied from the scene's `D24FS8` surface at each predicated tile's resolve, a 256-row band at a time, into an R32F image (sample 0, host value doubled); the scene surface of the previous frame decides which surface that is, since shadow depths come first. The swap's compute pass then writes the providers' depth and motion beside the HUD-less copy. Two surprises, found with `present_upscaler_view=depth|motion`: the scene is drawn turned 180 degrees in clip space, and its stored depth is reversed by the depth range, not the matrix, so the pass samples the opposite pixel, negates clip x and y around the reprojection, and uses 1 minus the stored depth, which is also the usual D3D depth the providers expect (`site/findings/rendering.toml`). Result on the drive route (RTX 4080, FSR 3.1.4, 1280x720 to 3840x2160): trees, road markings and the guardrail stay sharp, where without the inputs they smear into a painted look. The first attempt took the depth at the first HUD draw and got only the last tile's 256 rows, so the inputs were never used; the streaks seen then were FSR without inputs. Left: cars and other moving objects get the camera's motion, not their own (an object-motion pass would need a per-pixel object id, UP-1.7). Cost not measured separately; `present_upscaler_camera=false` turns it off |
| UP-1.1 honest dispatch | Done on multivac (2026-10-16) | The temporal upscale runs once per new guest frame: the presenter numbers every guest output refresh, and a repaint of the same frame shows the last upscale instead of feeding the frame twice. The frame delta is the measured time between guest frames, clamped to 1-100 ms; the history resets only when the provider, the source or output size, or the output image changes. SDR guest output gets `FFX_UPSCALE_ENABLE_NON_LINEAR_COLORSPACE` and the per-dispatch sRGB flag instead of the HDR and auto-exposure flags the old path set. Missing inputs get stand-ins (depth at the far plane, zero motion) at render size, so the dispatch costs what it will with real inputs. Cost (`present_upscaler_profile`: GPU timestamps around the dispatch, mean of 300 upscales, free-roam route, RTX 4080, 1280x720 to 3840x2160): FSR 3.1.4 0.72 ms, FSR 2.3.3 0.675 ms in steady state (1.0-1.3 ms in the first windows while loading). Measured on the Deck, Android and macOS with FSR from source in UP-2.1 |
| UP-1.2 HUD-less input and composite | Done (2026-10-16) | The HUD is not redirected to its own surface: the swap writes a second, HUD-less copy of each guest frame instead. FH1 draws its HUD last into the front buffer through the `2_10_10_10_AS_10_10_10_10` view, and the executor already snapshots the scene before the first HUD draw for HDR and the scene-only post. When the presenter asks for it (`WantsHudlessGuestOutput`, set while a temporal provider reads the guest output directly), the swap puts that snapshot through the same gamma-ramp compute pass as the frame, into a second image beside the guest output image, and the HDR HUD-mask pass writes the HUD coverage into its alpha (any change above 8-bit rounding, grown by a pixel for antialiased edges). The provider gets that image as colour; then `upscale_hud_composite.cs.glsl` blends the guest frame with the HUD, upscaled bilinearly, over the upscale by the coverage. Checked on the free-roam route with FSR 3 on the RTX 4080: `present_upscaler_hud=debug` shows the whole frame without the event banner, minimap or speedometer, the road under them intact and the colours matching the guest frame, so the gamma ramp and channel order hold; `composite` shows the HUD back on top. Limits: the HUD keeps the game's resolution (bilinear, not redrawn at the output size); under translucent HUD elements the scene is the bilinear one; a flow that downscales before the temporal slot (a quality mode below the guest resolution) still feeds the frame with the HUD; frames without a snapshot (menus) go whole; the LUT of the scene-only post is not in the HUD-less copy. The composite's own GPU cost was not timed (one compute pass over the output) |
| UP-0.3 provider interface | Done (2026-10-16), ShiftGlue `f7e4609` | `rex/ui/upscaler.h` (kind, id, version, modes, inputs used; the shared mode ratios 1, 1.5, 1.7, 2, 3) and `rex/ui/vulkan/upscaler.h` (`Prepare` for maximum sizes, `Dispatch` with an input set of colour, depth, motion vectors, reactive and transparency masks and per-frame data, `Release`). Bilinear, CAS and FSR 1 stay passes of the paint flow and are listed as spatial providers; their code path is unchanged (a temporal provider only replaces the flow's EASU slot), so they were not re-captured for a bit-exact check: routes diverge in traffic between runs, so presented frames of two runs are not comparable pixel for pixel anyway. FSR 2 and FSR 3 are providers over the FidelityFX API: linked when the SDK is built from source, otherwise loaded at run time from AMD's signed `amd_fidelityfx_vk.dll` in `upscalers/fidelityfx/<version>/` (newest first) or `present_ffx_runtime`. Only the MIT API headers are needed to build; `cmake/rexglue_ffx_api_headers.cmake` downloads four of them, pinned by SHA-256, from the same fork commit as the source build. The 1.1.4 runtime lists FSR 3.1.4 and 2.3.3, and each provider pins its version with the API's version override. Without the runtime both report the reason and the flow keeps FSR 1 EASU (checked on a route with a missing path). The old path's FidelityFX members, compiled only with a private define, also changed the class layout between targets; the providers are held by pointer now. New for testing: `present_capture_readable` keeps a copy of each painted frame, and render-test captures then also write `<name>-presented.ppm`, the image after the upscaler. Left for later items: the setup fetch of the runtime (UP-0.4) and a player setting (UP-8) |
| UP-0.2 capability matrix | Done (2026-10-16) | The SDKs were fetched into `.local/upscaler-sdks` (DLSS 310.9.16, Streamline 2.14.16, XeSS `de0fb9c`, NIS 1.0.3, FidelityFX 1.1.4 and 2.3.0). `tools/upscaler_probe.cpp` creates a Vulkan 1.3 device and asks each runtime for support without dispatching. **RTX 4080, driver 581.08**: NGX reports DLSS SR and DLSS frame generation supported and available on Vulkan (minimum architecture 0x160 and 0x190, that is Turing for SR and Ada for frame generation); XeSS creates a Vulkan context (`libxess` from the 3.0.2 SDK reports itself as 2.0.2; 4K Quality wants 2259x1271 input, a ratio of 1.7, so our integer scales need its "custom ratio" or ultra-performance modes); the FidelityFX 1.1.4 Vulkan DLL lists upscaler versions 3.1.4 and 2.3.3 and frame generation 1.1.3, and creates a 720p-to-4K upscaler context. The FidelityFX Vulkan backend calls `vkGetBufferMemoryRequirements2KHR` even on Vulkan 1.3 and crashes on a null pointer unless `VK_KHR_get_memory_requirements2` is enabled, so the integration must enable it. Extensions on the 4080: `VK_NV_low_latency2`, present id and wait, external memory and semaphores (the D3D12 bridge), FP16 and integer dot product; no `VK_AMD_anti_lag`. **Steam Deck (RADV, Mesa 24.3)**: present id and wait, FP16, integer dot product, subgroup size control and `VK_KHR_get_memory_requirements2`; no `VK_AMD_anti_lag` and no `VK_NV_low_latency2`, so the Deck's latency aid is our own limiter (UP-4.2). From the SDK files: the DLSS SDK ships Linux x86-64 and aarch64 NGX libraries for SR, ray reconstruction and frame generation, and NGX searches extra folders for the feature DLLs (`NVSDK_NGX_FeatureCommonInfo::PathListInfo`), so the drop-in folder is supported by the API; XeSS ships Windows binaries only, with Vulkan for SR and D3D12 only for frame generation (`xefg_swapchain_d3d12.h`) and XeLL (`xell_d3d12.h`); FidelityFX 2.x has no Vulkan backend, 1.1.4 has `amd_fidelityfx_vk.dll` and a Vulkan frame generation swapchain. Not run: the probe on AMD and Intel GPUs, and a Linux build of it (NGX on the Deck is moot: no RTX) |
| UP-0.1 licences | Policy written (2026-10-16) | `docs/LEGAL.md` now has a section on upscaler runtimes: no vendor files committed or shipped; open-source code (FSR 1-3, NIS, Arm ASR, SGSR) and redistributable binaries (FidelityFX DLLs, XeSS) fetched at setup with their notices; DLSS opt-in behind NVIDIA's licence, linked locally, plus a drop-in folder; `Lossless.dll` only from the player's install. Licence texts read: NIS is MIT; the XeSS binaries are under the Intel Simplified Software License (no modification or reverse engineering) and its public headers became MIT in 2026-09; the DLSS licence (RTX SDK) allows object-code distribution inside an application, forbids subjecting the SDK to an open-source licence (§4(e)), requires NVIDIA marks with NVIDIA's prior approval on the splash, about box and credits of applications incorporating DLSS or NGX, and notice before a commercial release. No Lossless Scaling terms beyond Steam's were found; lsfg-vk users select a dedicated Steam beta branch of Lossless Scaling, which suggests THS cooperates with that project. Still open: the letters to NVIDIA and THS (drafted, not sent; the maintainer sends them), and `THIRD_PARTY_NOTICES.md` entries once setup fetches the first runtime (UP-0.4) |
| UP-5.1 Lossless Scaling over the window | Windows partly verified (2026-10-16) | Lossless Scaling (Steam build 19655272) on multivac, RTX 4080, 4K 120 Hz HDR display with G-SYNC: the game ran at 1x with the 60 fps limit in its borderless window, from a private copy of a render seed. With LSFG 3, 2x, scaling off, started by its hotkey (Ctrl+Alt+S), LS opened its output window over the game and used about 16 % of the 3D engine (none with it off), with the game at 12-29 %. What the display showed could not be measured from here: desktop duplication reports 60 updates a second either way (LS's output does not go through it), and PresentMon needs administrator rights. The maintainer's own look at LS's frame counter, or an elevated PresentMon capture, closes it. The steps are on the site's playing page |
| UP-5.1 lsfg-vk on the Steam Deck | Done (2026-10-16) | With the maintainer's go-ahead: lsfg-vk 1.0.0 (the last MIT release, `lsfg-vk_noui.zip`) and the maintainer's `Lossless.dll` (Steam build 19655272) copied to `~/pinyon-qual/lsfg`, the layer loaded for the game's process only (`VK_ADD_IMPLICIT_LAYER_PATH`, `LSFG_LEGACY=1` with the DLL path, 2x, flow scale 1.0), started from a temporary Steam shortcut so the GPU ran at game clocks (1040 MHz), the Deck build of 2026-10-15 on a private copy of the play state with the game limited to 30 fps, at the title screen. MangoHud, loaded below lsfg-vk, counted the presents gamescope received over 40 s: 32.2 a second without lsfg-vk (GPU 14 % busy), 60.1 with it (GPU 61-66 %). lsfg-vk extracted the shaders from the DLL without errors. Two pitfalls: forcing the layer through `VK_INSTANCE_LAYERS` breaks it (the device it creates for itself loads the layer too and fails with `VK_ERROR_INITIALIZATION_FAILED`; its own manifest avoids that with `DISABLE_LSFG`), and lsfg-vk writes a default `~/.config/lsfg-vk/conf.toml` on first run (removed afterwards). The present calls come in pairs (half under 4 ms after the previous, half at 33 ms) with FIFO or the default present mode, because lsfg-vk queues the generated and the real frame together; whether the screen shows them evenly needs a look at the Deck or gamescope's own timing. The shortcut and state copy were removed; the layer, the DLL and the scripts stay in `~/pinyon-qual/lsfg` (10 MB) for UP-5.2 |
| Planning | Created (2026-10-16) | Licences, versions and forks checked on 2026-10-16. Current versions: DLSS SDK 310.9.16 and Streamline 2.14.16, FidelityFX SDK 2.3.0 (FSR 4.1.1, 3.1.5, 2.3.4; Vulkan unsupported in 2.x, supported in 1.1.x), XeSS 3.0.2 (SR on Vulkan, frame generation D3D12 only), SGSR 1/2 (BSD-3), Arm ASR (MIT), lsfg-vk (LSFG 3.1; licence changed from MIT to CC BY-NC-ND in 2026-08). No official FSR 4 Vulkan path as of the latest reports (2026-02) |
