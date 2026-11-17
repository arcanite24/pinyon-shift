# Third-party notices

Pinyon Shift downloads the following third-party projects during local setup.
Their own licenses apply; they are not relicensed by this repository.

- [ReXGlue SDK](https://github.com/rexglue/rexglue-sdk)
- [LLVM](https://github.com/llvm/llvm-project)
- [extract-xiso](https://github.com/XboxDev/extract-xiso)
- [Git for Windows](https://github.com/git-for-windows/git)
- [Microsoft Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)

Exact versions, source URLs, and archive hashes are recorded in
`config/release-toolchain.json`. ReXGlue's transitive dependencies are fetched
by its pinned source tree and retain their upstream notices.

Upscaler runtimes, downloaded by setup from their vendors' pinned commits
and checked by SHA-256, are staged beside the game in
`upscalers/<provider>/<version>/` with their licences:

- **NVIDIA DLSS** (Windows): the DLSS SDK 310.9.16 from
  [NVIDIA/DLSS](https://github.com/NVIDIA/DLSS): the NGX headers and static
  loader linked into the game, `nvngx_dlss.dll` and, for frame generation,
  `nvngx_dlssg.dll`. NVIDIA DLSS is a
  trademark of NVIDIA Corporation; this software uses the NVIDIA DLSS SDK
  under the NVIDIA RTX SDKs License (`upscalers/dlss/310.9.16/LICENSE.txt`).
- **AMD FidelityFX Super Resolution 2 and 3**: the FidelityFX SDK 1.1.4
  (MIT) from [rexglue/FidelityFX-SDK](https://github.com/rexglue/FidelityFX-SDK),
  AMD's signed `amd_fidelityfx_vk.dll` on Windows and the library built
  from that source on Linux, macOS and Android
  (`upscalers/fidelityfx/1.1.4/LICENSE.txt`).

LSFG frame generation, which runs only from the player's own Lossless
Scaling install, is built from two sources in
`thirdparty/shiftglue-sdk/thirdparty/lsfg` (see its `README.md`):
[lsfg-vk](https://github.com/PancakeTAS/lsfg-vk) 1.0.0's `framegen` (MIT,
`framegen/LICENSE.md`) and [DXVK](https://github.com/doitsujin/dxvk) 2.6.2's
DXBC compiler (zlib License, `dxbc/LICENSE`). No Lossless Scaling code or
shaders are included.

The Vulkan shader-mod loader statically links the SDK's pinned
[SPIRV-Tools](https://github.com/KhronosGroup/SPIRV-Tools) validator
(Apache License 2.0, in `thirdparty/shiftglue-sdk/thirdparty/spirv-tools/LICENSE`).

The launcher's racing wheel screen loads `SDL3.dll`, built from the SDK's
pinned [SDL](https://github.com/libsdl-org/SDL) source (zlib License, in
`thirdparty/shiftglue-sdk/thirdparty/sdl3/LICENSE.txt`).
