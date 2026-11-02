# MediaTek and Mali backlog

Created 2026-11-01 at `dev` `320255ce` (ShiftGlue `38f02553`). Goal: make
the game run as well as it can on MediaTek SoCs with Arm Mali / Immortalis
GPUs, starting from the Galaxy Tab S10 Ultra, and make what is learned there
apply to other Mali devices (Pixel Tensor, Exynos before Xclipse, Dimensity
phones). The Adreno backlogs
([ANDROID_60FPS_BACKLOG.md](ANDROID_60FPS_BACKLOG.md),
[ANDROID_ODIN_BACKLOG.md](ANDROID_ODIN_BACKLOG.md)) tuned for a GPU that can
render a pass in system memory and samples BC textures natively; Mali does
neither, so their rejected items are re-checked here only where that
difference is the reason.

**Status, 2026-11-02: closed for the S10 Ultra.** Both driver crashes are
fixed (MT-0.1, MT-0.2; 13 of 13 races since). Two defaults cut the busiest
stretch of the race from 22.6 to 20.1 ms a frame and the frames over 33 ms
from about 20 to 4-5 a run (MT-1.9, MT-1.6). Every other lever measured
below gave nothing, was slower or broke the image, and a custom driver is
not possible on this kernel (MT-2.2). What is left is fragment work in the
main scene and 2.4 ms of resolves; going further means a lower render
scale, shelved in RENDER_SCALE_BACKLOG.md. Reopen with a second MediaTek or
Mali device (the fixes are verified on this tablet and, for no regression,
on the Odin 2 Portal) or a device that gains 25 % from the render-scale
probe.

## Device

| | Galaxy Tab S10 Ultra (SM-X920) |
| --- | --- |
| SoC | MediaTek MT6989 (Dimensity 9300+) |
| CPU | 1x Cortex-X4 3.4 GHz, 3x X4 2.85 GHz, 4x A720 2.0 GHz (no little cores) |
| GPU | Mali-G720 Immortalis MC12, Vulkan 1.3.247 |
| Driver | Arm DDK r44p1 (`Valhall r44p1-01eac0`), the system driver |
| RAM | 12 GB |
| Display | 2960x1848, 120 Hz |

The route is `fh1-race-sustained` from the pinned seed `appdata-2026-09-27`
in a private state root (`files/qualification/<run>`), with
`--vulkan_require_vertex_pipeline_stores_and_atomics=false` (Mali has no
vertex stores) and the game's Android defaults: 1x, MSAA single-sampled
(`fh1_msaa_single_sample`), bloom, motion blur and depth of field off, the
60 fps limit off for measurement. Numbers are medians over the window from
the `race-ready` to the `race-sustained` capture. The race is not deterministic: the AI and the player car's line differ between runs, and the median draw count of the window ranged from 1,470 to 2,400. GPU time follows the draw count, so probes are compared by the submission-busy median over frames in the same draw-count band (1,000-1,500, 1,500-2,000, 2,000-2,400, 2,400-3,000), not by the window median. The tablet heats quickly
(the AP sensor went from 30 to 48 °C in one route, the skin to 39 °C, the
first throttle step), so each run starts below 32 °C on the AP sensor.

## Baseline

| Run | Frame | GPU frame | Submission busy | Process CPU | Decoder | Title thread | RSS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fix1 | 21.75 ms | 21.26 | 21.02 | 57.0 | 12.5 | 10.1 | 2.69 GB |
| fix2 | 22.98 | 22.25 | 21.99 | 62.6 | 13.5 | 10.6 | 2.60 GB |

The GPU decides the frame. With every draw's rasterization discarded
(`vulkan_debug_discard_rasterization`) the frame falls to the 16.67 ms
vsync floor and the submission worker's busy time (which includes waiting
for the GPU) from 21.0 to 4.8 ms. The guest-frame GPU time stays at 16.1 ms
there because it spans the gaps between the frame's submissions; it is a
wall-clock span, not GPU busy time, so a frame bound by the CPU also shows
it near the frame time.

GPU time by rendering (`fh1_native_gpu_profile`, 600 frames): the main
scene, `1024/32/4x/d1+0/32/4x/c3`, 9.9-10.4 ms in 20-34 renderings a frame;
`0/16/1x/c3` 2.3 ms; `0/16/1x/c2` 1.6 ms; resolves 2.5-2.7 ms, transfers
1.8 ms, clears 0.3 ms.

## Findings

| Item | Result |
| --- | --- |
| MT-0.1 Bindless set over the per-set limit | **Fixed** (ShiftGlue `38f02553`). The bindless set held 573,728 descriptors against `maxPerSetDescriptors` 500,000; the layout was still created and the driver crashed in `vkCmdDrawIndexed` about 20 s into the race in every run. The sampler binding now shrinks to fit (426,272 samplers here). |
| MT-0.2 Driver crash in `vkCmdEndQuery` | **Fixed** (ShiftGlue, this backlog): 10 of 10 races finished, against about half crashing before. After MT-0.1 the driver still segfaulted in about half the races, about 20 s in, always reading offset `0x38` through a null pointer. The Android fault handler now logs the registers (`rex-fault` in logcat), and replay breadcrumbs showed the faulting command was `vkCmdEndQuery` of the title's occlusion query pool, with one query begun and two ended in that command buffer. ShiftGlue ended a query twice: `DisableHostOcclusionQueries` (the title began a query while another was open, or ended one at another address) recorded the end, then called `EndSubmission`, which still saw the query active and recorded a second end. Ending an inactive query is invalid on every GPU (VUID-vkCmdEndQuery-None-01923); Adreno, AMD and NVIDIA ignored it, Mali dereferences null. The query state is now cleared before the submission ends. With the title's occlusion queries off (`occlusion_query_enable=false`) 0 of 4 races had crashed against 2 of 4. Ruled out on the way: the quad-list geometry shader (5 of 9 crashed with quad lists as triangle lists), pipeline creation racing command recording (3 of 6 crashed serialized), queries with no render pass inside (begun lazily, 2 of 8 crashed), bindless textures. The texture-sign pipeline seen being created at each crash was a coincidence of timing, and the crash-rate differences between small samples were noise. |
| MT-1.1 Attachment load/store ceiling | **No gain.** `fh1_debug_attachment_ops=7` (no loads, no MSAA stores, no depth stores) measured 22.03 ms, GPU 21.63, against 21.75-22.98 at baseline. Tile loads and stores at the 20-34 rendering breaks a frame are not what the frame waits for, so merging renderings (the rejected GPU pass P1 upload hoist) is not retried for Mali. |
| MT-1.2 Bindless textures off | **No gain.** `vulkan_bindless_textures=false`: 22.33 ms, GPU 21.81. |
| MT-1.4 AFBC census | `vulkan_image_compression_report` (ShiftGlue, this backlog) asks the driver per kind of image. Every surface (colour and depth) and every texture without storage usage is compressed. The textures resolves write directly through a raw `R32_UINT` storage view (single-level 2D textures, `vulkan_texture_load_compute_copy` and `vulkan_small_texture_copy_views`, usage `0xE`, flags mutable and extended usage) are not: 1280x720 colour and depth copies the post passes sample every frame. |
| MT-1.4b Copy views off for AFBC | **Slower.** With the raw storage views off (`vulkan_texture_load_compute_copy=false`, `vulkan_small_texture_copy_views=false`) the resolve textures are compressed but reloaded instead of written: 22.83 ms, 52 frames over 33 ms, against 21.74 ms and 16 in the paired baseline. Kept on. |
| MT-1.5 Texture bandwidth | **Not the limit.** Textures capped at 512 texels (`vulkan_texture_max_size=512`): 22.02 ms against 21.74. Sampling RGBA8 where Adreno samples BC costs memory (about 2.6 GB resident against the Odin's 1.3 GB, AP-2.4) but not frame time here, so a BC transcoder to ASTC or ETC2 is a memory item for 8 GB devices, not a speed one. A mip LOD bias of +1 measured 20.54 ms over a window with a third fewer draws (1,470 against 2,244): not comparable. |
| MT-2.2 Custom drivers | **Not feasible today.** Mesa's PanVK needs the upstream `panthor` kernel driver; this kernel has Arm's `kbase` (`/dev/mali0`), which Mesa does not drive. Arm's own driver is an Android HAL module (`vulkan.mali.so`, 10 KB, exports `HMI` and loads `libGLES_mali.so`, 46 MB): it exports no `vkGetInstanceProcAddr` and implements no surfaces or swapchains, only the gralloc hooks (`vkGetSwapchainGrallocUsage*ANDROID`, `vkAcquireImageANDROID`, `vkQueueSignalReleaseImageANDROID`) Android's loader builds `VK_KHR_swapchain` on. Loading another Arm DDK from the app, as libadrenotools does for Turnip (which brings its own swapchain), would mean reimplementing Android's swapchain layer over gralloc, and would still need a DDK whose kernel interface matches this `kbase`. |
| MT-1.7 Fragment cost by pixels | `fh1_debug_raster_percent=50` (half the rows of the pitch-16 surfaces rasterized, wrong image): 18.58 ms, submission busy 17.8 against 21-22. Fragment work scales with pixels; a cheaper pixel is worth about 7 ms a frame at full coverage. |
| MT-2.1 Updatable drivers | **None to use.** The system names `com.samsung.gamedriver.mt6989` and `com.samsung.pregpudriver.mt6989` as its updatable drivers (`ro.gfx.driver.0/1`); both are 21 KB placeholder packages with no driver library, which Galaxy Store updates would fill, and Android accepts an update only signed with Samsung's key. |
| MT-1.8 Relaxed precision in pixel shaders | **No gain.** A probe build decorated the float arithmetic results of every translated pixel shader `RelaxedPrecision`, which lets Mali compute them at 16 bits (the captures matched the baseline within run-to-run noise; texture coordinates mostly come from interpolants, which it left alone). Submission busy over frames with 1,500-3,000 draws: 21.9-23.3 ms against 21.6-22.8 at baseline. The pixel shaders are not ALU-bound here; the probe was not kept. |
| MT-3.1 Decoder on the X4 cores | **No gain.** `android_thread_cores=GPU_Commands=4-7`: 22.2-23.3 ms in the same bands against 21.6-22.8. The frame waits for the GPU, and the scheduler already runs the decoder on a big core. |
| MT-1.3 Robust buffer access off | **No gain.** A probe switch for `robustBufferAccess`, two cooled runs interleaved with baselines: 21.2-22.4 ms in the 1,500-2,000 band, 22.3-22.8 at 2,400-3,000 draws, against 19.6-21.7 and 22.0-22.8. A first single run looked 2 ms faster, but its race took another line (a damaged car, never above 2,000 draws), the reason for the draw-band method. Kept on; the switch was not kept. |
| MT-1.6 Coarse shading of the main scene | **2.0-2.5 ms a frame, about 10 %.** `fh1_coarse_shading=1024/32/4x/d1+0/32/4x/c3=2x2` (the main scene once per 2x2 pixels), three cooled runs against four baselines: 17.3-17.6 ms in the 1,000-1,500 band against 19.2-21.0, 20.3-20.5 ms at 2,400-3,000 draws against 22.0-22.8. The captures look the same at the tablet's size. It is the existing SCENE SHADING > COARSE option (which also coarsens the shadow mask), and `vulkan_fragment_shading_rate` is already on for Android, so Mali players can choose it today; a new config on an Arm GPU with the extension now starts at COARSE (`ApplyFirstRunHardwareDefaults`; existing configs keep the player's choice). The full COARSE preset (scene, shadow mask and alpha-tested foliage) on top of MT-1.9, two runs: 20.07-20.17 ms at 2,400-3,000 draws against 21.45-21.76 without it, frames over 33 ms 4-5 against 10-17. |
| MT-1.9 Swapchain at the display's size | **0.8-1.2 ms a frame.** The tablet presented the 1280x720 frame into a 2960x1848 swapchain. Android's swapchain scales its images to the window, so the presenter now divides the swapchain by the largest whole number that still holds the game's output at the render scale (`android_present_divisor`, ShiftGlue; 0 automatic, 1 the display's size): 1480x924 here, unchanged on a 1080p phone. A display-size probe (`wm size 1480x924`) first saved 0.4-2 ms; the presenter change, two cooled runs each: 21.45-21.76 ms at 2,400-3,000 draws against 22.54-22.63 at the display's size, 20.9-21.5 against 21.9-22.0 at 2,000-2,400. The image fills the panel at the same proportions. |
| MT-1.10 Coarse shading of the post renderings | **Rejected: wrong image.** Adding `0/16/1x/c2` and `0/16/1x/c3` (1.6 and 1.8 ms a frame, 22 renderings) to the coarse list halved the submission-busy time (18-19 to 8.5-9.7 ms, the frame at the 16.7 ms vsync floor), far more than those renderings cost: the sky showed blocks, the HUD panels tiled and the lighting changed, so the gain was a broken post chain, not cheaper shading. |
| MT-1.11 Resolve cost ceiling | `fh1_debug_skip_resolve_dispatches` (wrong image) took the frame to the vsync floor; resolves cost 2.4 ms a frame by the GPU profile. They write through raw storage views the driver does not compress (MT-1.4), and letting them be compressed was slower (MT-1.4b). The two resolve options are already the faster setting here: with `fh1_resolve_to_textures=false` (textures reloaded instead of written by the resolve) 20.95-21.39 ms at 2,400-3,000 draws and 19.8-19.9 at 1,500-2,000, against 20.58-20.79 and 19.0-19.1 with the defaults (MT-1.6/1.9 on); with `fh1_resolve_two_textures=false` 21.43 and 19.39 in one run (the second took another route: 1,173 draws). |

## Where this leaves the tablet

The frame is decided by fragment work in the main scene (MT-1.7); loads and stores at rendering breaks (MT-1.1), texture bandwidth (MT-1.5), bindless (MT-1.2), shader precision (MT-1.8), robust access (MT-1.3) and the CPU (MT-3.1) are not the limit. Fewer pixels is what pays: fewer presented (MT-1.9), coarser shading (MT-1.6), both now defaults, which together take the busiest stretch of the race from 22.6 to 20.1 ms; beyond that, a lower render scale, which RENDER_SCALE_BACKLOG.md shelved for want of a device that gains 25 %; the tablet's 50 % raster probe (MT-1.7) saved 16 %, under that gate. A custom driver is not an option on this kernel (MT-2.2), and Samsung's updatable driver slots are empty (MT-2.1).
