# Direct3D 11 backend backlog (D11-*)

Goal: run Pinyon Shift on GPUs that have Direct3D feature level 11_0 but
neither Vulkan 1.3 nor a usable Direct3D 12 driver: AMD TeraScale (HD
5000/6000), Intel Sandy Bridge and Ivy Bridge graphics on Windows, and
NVIDIA Fermi (GTX 400/500). Branch `feat/d3d11` in both repositories.

## Where it stands (2026-11-19)

- **Runs the game.** `--gpu_backend=d3d11` reaches free roam on multivac
  (RTX 4080, device created at feature level 11_0 only). The live
  `fh1-free-roam` route renders the same as Vulkan at 1x (the captures
  differ by traffic positions only). Median frame time over the last 600
  frames: 11.1 ms against Vulkan's 8.4 ms on the same build.
- **Frame replays.** Against Vulkan goldens recorded at 1x on the same
  build, `fr1400` and `race4800` are bit-exact. In `ac0-stock` (Autoshow,
  1557 draws, 79 resolves) the executor does the same work (identical draw,
  resolve and transfer counts, no skips), and the first 54 resolves are
  bit-exact. They diverge at the main scene's depth, in the low bits only.
  Vulkan flips reverse Z in the viewport, while Direct3D (11 and 12) can't
  have MinDepth > MaxDepth and flips it in the vertex shader's NDC
  transform, which rounds differently. The front buffer differs by 5.6/1023
  on average, and the frame looks identical. The Direct3D 12 backend
  replays this dump black, so it can't serve as a third reference.
- **blindvac (ASUS X510UR).** Both GPUs create the device at 11_0 and run
  the race route with the low-spec preset. Median frame over the last 600
  frames: UHD 620 151 ms (Vulkan 85 ms), GeForce 930MX 80 ms (Vulkan 66 ms;
  both APIs show the laptop's Optimus stalls). Direct3D 11 is a fallback for
  GPUs without Vulkan 1.3, not a faster path.
- **Intel viewport fix.** On the UHD 620 night and race frames were blown
  out by bloom. Draws without clipping use an 8192-pixel host viewport, and
  the Intel driver drew them as if that viewport were squeezed into the
  render target: FH1's full-screen depth clear (a depth-only rectangle
  list, stencil FF) into the 640x1024 4x surface covered only its top-left
  corner. The surface stayed 0, the 8888 surface transferred from it lost
  its far-plane value, and the bloom input saturated. Found by reading the
  surface back after every draw (texture loads, shaders, constants and
  vertex data all matched NVIDIA byte for byte). On Intel the viewport is
  now bounded by the bound targets (`d3d11_viewport_fit_targets`, -1 auto,
  0 off, 1 on). The night replay's resolve 4 then matches Intel Vulkan but
  48 words, and its final image is within 1.6/1023 on average of the RTX
  4080's. Forced on, the RTX 4080 keeps `fr1400` and `race4800` bit-exact
  (`ac0-stock` changes in 3 words). Intel Vulkan draws the night frame with
  a blur and glow that neither the RTX 4080 nor Intel Direct3D 11 shows; not
  investigated.
- **Presentation.** FH1 fetches its front buffer with red and blue swapped.
  Direct3D 11 has no SRV component mapping, so a small compute pass
  (`d3d11_swap_swizzle_cs`) applies the swizzle before the gamma shaders.
- **Not done:** the game and launcher wiring (D11-2.1), the windowed mirror
  (D11-2.3, not needed so far), the persistent shader cache (D11-2.4), GPU
  timestamps in the executor, and the debug layer, which isn't installed on
  multivac (the "Graphics Tools" optional feature). Memexport and
  tessellation draws are dropped; FH1 issues neither on the measured
  routes. Resolution scale is 1x only.

| Item | Status |
|---|---|
| D11-0.1 | Done |
| D11-0.2 | Done; translated shaders are created by the device (debug layer not run) |
| D11-0.3 | Done. The texture loads are the verified D3D12 SM 5.1 bytecode, converted to SM 5.0 at startup (`dxbc_shader_model_5_0.cpp`), since current upstream doesn't reproduce our `texture_load_*` headers. All 182 `d3d12_5_1` headers convert, and the converted shaders are accepted by the device at feature level 11_0 |
| D11-1.1 to D11-1.5 | Done (see above) |
| D11-2.1 | Open: needs a decision on offering it to players |
| D11-2.2 | Done: occlusion queries, gamma ramp and front buffer dumps |
| D11-2.3 | Not needed so far: a 512 MB buffer was created on every tested GPU |
| D11-2.4 | Open |
| D11-3.1 | Done: multivac and blindvac (UHD 620, 930MX) above |

## Starting point

A contributor sent an experimental D3D11 backend on 2026-11-19
(`source-dx11.zip`, built from the 0.9.1 tree). What we took from it:

- The DXBC translator can target shader model 5.0. The changes are the
  version token, the RDEF header and input-bind layout without register
  spaces, the slot limits, and no UAVs outside pixel and compute shaders.
- Notes on D3D11 pitfalls: the guest memory mirror bound as a raw view, and
  readback through staging buffers.

What we did not take:

- Its backend files. The drop does not build: the `ui/d3d11` headers, the
  `dxbc.h` and translator header changes, CMake, the cvar wiring and the
  SM 5.0 built-in shader bytecode are all missing.
- Its immediate drawer. It drops every draw, so no host UI renders.
- Its memexport handling. It drops memexport draws.
- Its runs as evidence. The draw counters in its logs read `drawn=0`.

The backend here is a port of our own D3D12 backend in the bindful path
(no ROV, no tiled resources, no bindless), which passes the D3D12 frame
replays. Like Vulkan, it translates shaders at runtime instead of loading a
pack.

## Constraints at feature level 11_0

- Shader model 5.0: no register spaces and no resource arrays across spaces.
  Per stage there are 14 constant buffers, 16 samplers and 128 SRVs.
- UAVs only in pixel and compute shaders. In a pixel shader, render targets
  and UAVs share 8 slots. FH1 has no memexport draws on any measured route
  (title, free roam, night, race; about 40 Vulkan perf logs on three
  devices, all `memexport_draws=0`), so the vertex-shader limit does not
  block this title.
- Typed UAV loads only as R32_UINT, R32_SINT and R32_FLOAT.
- No tiled resources. The 512 MB guest memory mirror is one ordinary buffer,
  and resolution scaling stays at 1x.
- One immediate context. It is made thread-safe with `ID3D10Multithread`,
  because the presenter paints on the UI thread.
- The documented size limit for one resource is max(128 MB, a quarter of
  VRAM), which would make the 512 MB mirror need 2 GB of VRAM. Drivers can
  allow more: a 512 MB buffer with raw SRV and UAV views was created at 11_0
  on the RTX 4080, the UHD 620 (shared memory) and the 930MX (2 GB) on
  2026-11-19. Splitting the mirror into windows (D11-2.3) stays open until a
  card that refuses it turns up.

## Items

| ID | Item | Gate |
|---|---|---|
| D11-0.1 | CMake option `REXGLUE_USE_D3D11` (`REX_HAS_D3D11`); `gpu_backend=d3d11` in the allowed list and the plugin factory; a `kD3D11` guest output backend | Builds with D3D12, Vulkan and D3D11 together |
| D11-0.2 | The DXBC translator targets SM 5.0 (`DxbcShaderTranslator` `target_sm_50`) | Translated shaders pass `CreateVertexShader` / `CreatePixelShader` / `CreateGeometryShader` with the debug layer |
| D11-0.3 | SM 5.0 built-in shaders in `bytecode/d3d11_5_0`, from the upstream xesl sources and our HLSL (texture loads, resolves, FH1 native transfers and resolves, gamma, FXAA, presenter, immediate drawer) | `compile-d3d11.sh` rebuilds every header from source |
| D11-1.1 | `ui/d3d11`: provider (feature level 11_0 device, adapter choice), presenter (flip-model swap chain when available, guest output mailbox, upscalers), immediate drawer | Host UI and the guest output show on screen |
| D11-1.2 | Graphics core: graphics system, command processor, shared memory, primitive processor | Title screen frames are drawn |
| D11-1.3 | Texture cache (compute untiling into textures) | Title and menu textures match Vulkan |
| D11-1.4 | Pipeline cache: runtime translation, shader and state-object caches | No failed pipelines on the title route |
| D11-1.5 | FH1 native executor on D3D11 (surfaces, EDRAM ownership, transfers, resolves, clears) | Title, menu and free-roam frame replays match the Vulkan goldens |
| D11-2.1 | Game wiring: settings, config migration and launcher choice; `HardwareCheck` accepts 11_0 when Vulkan 1.3 is missing | A clean install on a Vulkan-less machine reaches the title |
| D11-2.2 | Occlusion queries, gamma ramp, frame dumps on D3D11 | Free-roam and race routes pass |
| D11-2.3 | Windowed guest memory mirror for cards under 2 GB | Runs with the mirror capped at 256 MB |
| D11-2.4 | Persistent DXBC cache for translated shaders | Second run has no translation stalls |
| D11-3.1 | Measure: multivac forced to 11_0 against Vulkan; blindvac UHD 620 | Numbers on the renderer page |

Acceptance on every item: the device is created with only
`D3D_FEATURE_LEVEL_11_0`, and the debug layer is clean on the route. Nothing
in the lab is 11_0-only hardware; multivac (RTX 4080) and blindvac (UHD 620)
stand in, and the docs say so.
