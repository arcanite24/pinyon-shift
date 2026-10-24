# Android minimum requirements

Audit date: 2026-10-24. Source baseline: Pinyon Shift `34e2f00c`,
ShiftGlue `102fe952422680855291a213cc47a7abfc616ea1`, NDK r29
(`29.0.14206865`). This is a source and history audit, with small compiler
probes, not a new device qualification or a performance experiment.

The shipped requirements remain **Android 13 / API 33, ARMv8.2-A and a
Vulkan 1.3 driver**. None is an unused declaration that can safely be
removed on the evidence available here. However, none proves that the
whole game intrinsically needs that exact version either.

| Minimum | Recommendation | Candidate and cost |
| --- | --- | --- |
| Android 13 / API 33 | **Needs hardware.** Qualify a lower floor first. | API 30 (Android 11): bounded Java compatibility changes, a complete native rebuild and installation/lifecycle/update tests on an older OS. API 26 is a larger platform port. |
| Vulkan 1.3 | **Needs hardware.** Keep the advertised floor until an older driver passes. | Vulkan 1.2 **with dynamic rendering**: audit extension dependencies and qualify formats, shaders and memory. Vulkan 1.1 without dynamic rendering loses the FH1 executor and needs substantially more work. |
| ARMv8.2-A | **Needs hardware.** An ARMv8.0 build is technically plausible. | Compile all native targets for `armv8-a`, update the Java guard and provenance, and test a CPU without LSE. No retranslation should be necessary. |

Prioritize API 30 qualification and a Vulkan 1.2 driver before a separate
ARMv8.0 package. Lowering one limit only admits devices that pass the other
two, plus memory and driver correctness checks. The available Odin 2 Portal
and Astra can catch regressions; they cannot qualify old Android releases,
non-LSE CPUs or a genuine older GPU driver by passing on their newer hardware.

## Why the floors were chosen

`git log -S` separates an original target choice from a later dependency:

| Floor | History and reason |
| --- | --- |
| API 33 | Root [`131e7696`](https://github.com/arcanite24/pinyon-shift/commit/131e7696) introduced `min_sdk: 33` in `config/android-toolchain.json` on 2026-10-01. The [port backlog](../ANDROID_PORT_BACKLOG.md#progress-2026-10-01) explicitly narrowed the target to Snapdragon 8 Gen 2+, 12 GB and Android 13. It does not establish API 33 as an engine requirement. |
| Vulkan 1.3 | The same commit introduced `android.hardware.vulkan.version = 0x403000` in `android/AndroidManifest.xml`. It was the declared driver class for that target. The SDK already had promoted-extension negotiation; SDK [`cbc34c28`](https://github.com/arcanite24/shiftglue-sdk/commit/cbc34c28) fixed the dynamic-rendering extension feature chain during Android bring-up. SDK [`773539d4`](https://github.com/arcanite24/shiftglue-sdk/commit/773539d4) later added the diagnostic API-version cap for #618. |
| ARMv8.2 | Root [`9bdd4314`](https://github.com/arcanite24/pinyon-shift/commit/9bdd4314) raised **every Android target** to `-march=armv8.2-a` on 2026-10-14, to inline LSE atomics and remove outline helper calls. Before that, the SDK's default was `armv8-a`. The same change added the pre-library CPU guard. |

Existing compatibility work is substantial: custom-driver import and Vulkan
testing, automatic bundled Turnip on Adreno 7xx/8xx, presets, geometry-shader
fallbacks and the opt-in vertex-store workaround. This audit adds none of
those again. FH2's advertised Android 8 / Vulkan 1.1 / 4 GB support is a
reason to investigate coverage, not evidence that this different FH1
renderer will run correctly or quickly on the same phone. No FH2 code or
shader transformation was copied, translated or adapted for this audit.

## Vulkan: a feature contract, not just a version number

The [device layer] at `src/ui/vulkan/vulkan_device.cpp:294` negotiates
individual features and extensions. It does not reject every device below
1.3. The native executor and presenter have different requirements:

| Capability | Status in this baseline |
| --- | --- |
| `dynamicRendering` | **Required by the FH1 native executor** (`fh1_native_executor.cpp:469`). Available through core 1.3 or `VK_KHR_dynamic_rendering`; the SDK links the extension feature and loads the KHR entry points below 1.3 (`vulkan_device.cpp:635, 993, 1145`). |
| Missing dynamic rendering | Executor initialization fails and `command_processor.cpp:2560` falls back to the general render-target cache. Classic render-pass paths exist. This is not equivalent qualification of the shipped FH1 executor, its single-pass tiling path, image or speed. |
| Android presentation | `VK_KHR_surface`, `VK_KHR_android_surface`, `VK_KHR_swapchain`, a presentable surface/queue and usable swapchain formats are required. The [presenter] checks the extensions at lines 742–779. Its composition uses classic render passes and ordinary barriers (`vkCmdBeginRenderPass`, `vkCmdPipelineBarrier`), not mandatory dynamic rendering or synchronization2. |
| Descriptor indexing, core in 1.2 | **Optional optimization already implemented.** [Translator features] at lines 194–211 require runtime arrays, sampled-image update-after-bind, partially bound and update-unused-while-pending descriptors, dynamic sampled-image indexing and sufficient image/sampler limits before enabling bindless textures. Otherwise per-draw texture descriptors remain in use. Vulkan 1.1 currently takes that fallback even if its driver advertises `VK_EXT_descriptor_indexing`; this SDK does not negotiate that extension's feature structure below 1.2. |
| SPIR-V | Guest shader translation selects 1.5 for Vulkan 1.2+, 1.4 with `VK_KHR_spirv_1_4`, 1.3 for Vulkan 1.1, otherwise 1.0 ([translator features], lines 178–189; geometry pipeline generation does likewise). Checked-in FH1 resolve/transfer shaders are compiled with glslang `-V`; the inspected color-resolve module is SPIR-V 1.0. There is no blanket need to downgrade every shader header from 1.5 as in another renderer. Shader overrides and optional upscalers need separate qualification. |
| Timeline semaphores | Only enabled for the build-gated `gpu_async_fence_probe` experiment, not a normal release requirement (`vulkan_device.cpp:970`, `command_processor.cpp:8830`). Normal submission has fences/binary semaphores. |
| `synchronization2`, `bufferDeviceAddress`, GPU int8/float16 arithmetic | No mandatory feature request or use found in the FH1 executor/presenter paths audited. Do not confuse CPU FP16 instructions with GPU shader features. Optional FidelityFX upscalers have their own checks and are not proof of the basic renderer's floor. |
| Other promoted features | `samplerMirrorClampToEdge`, `uniformBufferStandardLayout`, `scalarBlockLayout`, float controls, image-format lists and maintenance/allocation extensions are queried/enabled where available. The device layer does not make the 1.2 layout flags a startup gate. `shaderDemoteToHelperInvocation` is optional via core 1.3 or `VK_EXT_shader_demote_to_helper_invocation`. Audit selected shader capabilities when qualifying a lower driver. |
| Optional extensions | Push descriptors fall back to allocated descriptor sets; `VK_EXT_robustness2` null descriptors fall back to actual null images. Memory-budget reporting, HDR metadata/colorspaces, present-id/wait, debug labels/checkpoints, pipeline statistics and fragment shading rate are optional. `VK_EXT_shader_stencil_export` accelerates stencil transfer when present; the executor retains a fallback. These do not establish a 1.3 floor. |

Version lowering does not remove older base requirements. GPU emulation
requires `independentBlend` and `fragmentStoresAndAtomics` in the device
selector. `vertexPipelineStoresAndAtomics` is required by default; the
existing Mali opt-in skips vertex memory-export writes, so it is a
correctness tradeoff, not universal support. Geometry shaders and non-solid
fill are not required by default on Android. See the existing
[Android troubleshooting](../ANDROID.md#troubleshooting).

Formats and allocation limits can fail even when the version passes.
The capability report checks sampled/color/storage use of
`A2B10G10R10_UNORM_PACK32` and a sampled depth/stencil format (D24S8 or the
D32S8 fallback). Without sparse buffer support, shared guest memory is a
dedicated **512 MB** allocation. BC texture decompression can need four to
eight times the texture memory; the log still identifies unchecked
multisampled-storage-image support as a risk. These costs make a 4 GB phone
a separate memory-pressure qualification, not a consequence of accepting
its Vulkan version ([device layer], lines 230–269).

### Cost of lowering Vulkan

**1.2 plus dynamic rendering is the smallest useful target.** Check the
feature bit as well as the extension, validate the KHR calls, and retain
the existing non-bindless route on drivers with small descriptor limits.
Record the driver's actual features/formats and test both native executor
and presenter. A diagnostic cap (`--vulkan_max_api_version_minor=2`) on a
modern GPU exercises negotiation, not that older GPU's limits or bugs.

**1.1 is more than a manifest edit.** The
[dynamic-rendering extension specification](https://docs.vulkan.org/refpages/latest/refpages/source/VK_KHR_dynamic_rendering.html)
requires its older-version dependency chain, including depth/stencil
resolve (and its dependencies), or Vulkan 1.2. The current request list
does not enable that whole chain for 1.1. Without dynamic rendering, either
qualify the general renderer at the resulting cost or add classic
render-pass support to the FH1 executor. Then validate shader capabilities,
format fallbacks and the non-bindless path on hardware. Do not advertise
1.1 merely because the device selector accepts it.

The manifest's `uses-feature` entry is informational metadata used for
distribution filtering. Android itself does not check it before installing
a sideloaded APK ([Android manifest reference](https://developer.android.com/guide/topics/manifest/uses-feature-element)).
Unlike `minSdkVersion` and the CPU guard, it is not by itself a universal
installation/startup barrier. The SDK's runtime feature checks still apply.
Do not count a manifest-only change as newly working phones.

The manifest describes the system's reported hardware, while a custom
Turnip driver can expose a different version/features after launch.
Changing the manifest alone neither upgrades the system driver nor proves
runtime compatibility. Android version also does not identify the GPU's
version: an upgraded Android 13 device may still have Vulkan 1.1
([Android Vulkan guidance](https://developer.android.com/games/develop/vulkan/native-engine-support)).

## CPU: why ARMv8.0 remains possible

`cmake/PinyonShiftRexGlue.cmake:143–152` sets
`PINYON_SHIFT_ANDROID_MARCH=armv8.2-a`, adds the compiler flag globally and
passes it as `REXGLUE_ARM64_MARCH` to the SDK. The SDK helper's own default
is `armv8-a` (`cmake/rexglue_helpers.cmake:176`). The Android preset's
`PINYON_SHIFT_CPU_BASELINE=armv8-a` is therefore not the effective Android
instruction limit. Provenance is separately hard-coded to `armv8.2-a` in
`tools/pinyon_android.py:386`.

The effective differences are:

- **LSE atomics:** enabled by the current flag. Guest store-conditionals
  are emitted as C++ atomic compare-exchange in
  `src/codegen/builders/helpers.h:306`, not hard-coded LSE assembly.
  Compiler targeting determines whether they become LSE, an outline
  helper or an LL/SC loop. Runtime atomics benefit in the same way.
- **RDM:** the flag enables rounded doubling multiply-accumulate support;
  `PinyonShiftActivity.java:159` checks `atomics` and `asimdrdm` before
  loading any native library. The check protects the chosen binary
  contract; it does not demonstrate that an FH1 algorithm intrinsically
  requires RDM. SIMDe can select implementations for the target.
- **Dot product and FP16 arithmetic:** neither `+dotprod` nor `+fp16` is
  requested. NDK r29 macro probes for plain `armv8.2-a` define atomics and
  QRDMX, but not dot-product or FP16 arithmetic feature macros. Baseline
  half-format conversion should not be confused with those optional
  arithmetic extensions. No mandatory dot-product/FP16 intrinsic was found
  in the host PPC/runtime paths searched.

An independently written probe including the SDK's PPC context and SIMD
intrinsics compiled for **both `armv8-a` and `armv8.2-a`**, targeting Android
API 30. The compare-exchange used an outline atomic helper in the former
and inline LSE in the latter. This establishes header/compiler feasibility,
not that a complete APK works on an ARMv8.0 CPU. Android's standard
[`arm64-v8a` ABI](https://developer.android.com/ndk/guides/abis#arm64-v8a)
itself only requires ARMv8.0.

The original [NN-1.11 measurement](../NEAR_NATIVE_RESEARCH.md) reported
outline calls falling from 1,976 to zero in `libmain`, 594 to zero in the
runtime and 71 to zero in the GPU library. Its three old-build and two
new-build Odin runs found **no per-thread runtime difference outside run
spread**. Those are historical measurements, not new R07 samples or a
precise zero-cost claim for a slower core.

### Cost of lowering the CPU baseline

Set `PINYON_SHIFT_ANDROID_MARCH=armv8-a` for a clean build of **all** native
libraries and facade modules, keep safe outline atomics (or explicitly
measure LL/SC), and align the Java guard and build manifest with that
target. Audit separately built libraries and imported driver binaries;
rebuilding only `libmain.so` leaves possible illegal instructions in its
dependencies. Keep the PowerPC memory-ordering fences. No codegen contract
change is indicated, so reuse frozen base/v4 generated sources.

The missing test is a real arm64 CPU whose HWCAP/cpuinfo lacks LSE/RDM:
startup/static initialization, atomic contention and guest synchronization,
base/v4 routes and a thermal soak. A modern Odin running an ARMv8.0 build
can still execute LSE through dynamically selected helpers, so it does not
exercise the old CPU path. Slower atomics may cost more on an older core;
no measured percentage is available for it.

## Android API: app and NDK dependencies

`config/android-toolchain.json` sets **minimum 33**, **target 35** and
**compile platform 36**. Packaging applies the minimum to aapt2, d8 and
`ANDROID_PLATFORM`, including the separate FidelityFX build. Lowering
target/compile SDK is unnecessary. Native API availability depends on the
minimum, not the Java compile SDK
([NDK SDK-version rules](https://developer.android.com/ndk/guides/sdk-versions)).

The installed SDK's API-36 `data/api-versions.xml` and NDK r29 headers give
the following concrete blockers and nearby boundaries:

| Use | API and consequence of lowering |
| --- | --- |
| `Intent.getParcelableExtra(String, Class)` in `SetupActivity.java:990` | **33**, unguarded in the package-update confirmation path. Use a version-gated legacy overload with a type check below 33, or updating fails there with a missing-method error. |
| `Context.RECEIVER_NOT_EXPORTED`, `SetupActivity.java:168` | **33 flag semantics**. The three-argument `registerReceiver` overload itself exists since **26**, so the flag is not evidence of a missing API-33 method. A lower-OS implementation must preserve the install-status receiver's isolation (for example, a compatible registration with an app-only permission), not simply remove protection. |
| POSIX crash reporter `backtrace` family | Bionic added these at **33**. `src/crash_reporter_posix.cpp:22` already compiles them out below 33; signal/library/offset reporting remains, but the current full stack trace is lost unless an older-compatible unwinder is added. Existing API-33 binaries must be rebuilt. |
| `PendingIntent.FLAG_MUTABLE`, `SetupActivity.java:975` | **31 constant**, inlined by Java. Audit/version-gate older-OS semantics for the install callback; a constant alone is not a missing-method failure. |
| `Build.SOC_MODEL`, activity line 237 | **31**, already guarded with `SDK_INT >= 31`; kernel GPU-model detection remains. Not a hard floor. |
| `Context.getDisplay()`, activity line 132 | **30**, unguarded display-diagnostics call. API 30 can keep it; API 26–29 needs the older window-manager display route. |
| `setShowWhenLocked` / `setTurnScreenOn` | **27**, used for scripted launches. Need guards/older window flags for an API-26 target. |
| `PackageInfo.getLongVersionCode()` | **28**, unguarded in setup's version check. Need the older `versionCode` below 28. |
| SDK shared mappings, `memory_posix.cpp:411` | Bionic `memfd_create` is **30**, called directly for Android guest shared memory. Below 30 needs a compatible mapping implementation, not just a Java edit. |
| SDK APC delivery, `threading_posix.cpp:1536` | `pthread_sigqueue` is **29**, used directly for per-thread guest callbacks. Below 29 needs a correct replacement for thread-targeted delivery, not process `sigqueue`. |

Sources: [Android Context reference](https://developer.android.com/reference/android/content/Context#RECEIVER_NOT_EXPORTED),
[Intent reference](https://developer.android.com/reference/android/content/Intent#getParcelableExtra(java.lang.String,%20java.lang.Class)),
and [bionic API history](https://android.googlesource.com/platform/bionic/+/main/docs/status.md).
No direct API-33 performance-hint or game-manager requirement was found
in the app Java/native glue. SDL supplies lifecycle, audio, input and the
surface; its newer optional platform paths must remain guarded.

### Cost of lowering the Android version

**API 30 is a bounded follow-up**, because it retains `memfd_create`,
thread-targeted APCs and the current display call. Fix the update/receiver
compatibility paths, accept or replace reduced crash unwinding, rebuild
every native dependency with the lower platform, and check dynamic symbol
imports and ELF notes/alignment. Reusing API-33 `.so` files in a lower-minSDK
APK is invalid. Preserve target 35, app-private saves and the installer
confirmation flow. Qualify setup from an empty private state, resumed
transfer, folder import, driver import, self-update/cancel, controls,
audio, pause/resume and background memory pressure on the old OS.

**API 26 / Android 8 is a larger port:** shared-memory fallback, APC
delivery, the Java API boundaries above, loader/driver compatibility and
old-kernel mapping behavior all need work. The NDK's support for old APIs
does not supply those missing runtime services. The current bundled
driver's metadata advertises API 28, and imported drivers have their own
minimums; the pinned libadrenotools also documents Android 9+ support in
`thirdparty/libadrenotools/README.md`. An API-26 port must disable that path
there or extend and qualify it. Custom Vulkan import cannot repair an
OS-symbol dependency.
Keep driver selection and import testing rather than force a driver on an
unsupported GPU/OS.

## Installed-base opportunity: what public data can establish

These are dated, marginal coverage estimates, **not counts of phones that
can run FH1**. No public cross-tab of Android version, LSE/RDM, our Vulkan
feature/format contract, RAM and sustained performance was found.

[Google's public Android Studio distribution metadata](https://dl.google.com/android/studio/metadata/distributions.json),
retrieved 2026-10-24, labels its update **2025-12-01**. Summing its rounded
`distributionPercentage` entries gives:

| OS floor | Share at/above floor | Gain over API 33 |
| --- | ---: | ---: |
| API 33 / Android 13 | 57.8% | — |
| API 31 / Android 12 | 69.2% | +11.4 percentage points |
| API 30 / Android 11 | 82.9% | +25.1 points (43.4% relative) |
| API 26 / Android 8 | 98.3% | +40.5 points |

This is an older Google distribution snapshot, not October 2026 adoption.
The OS-only gain is an upper bound before applying other requirements;
there is no defensible absolute device count or guaranteed FH1 gain.

[Google's Vulkan dashboard](https://developer.android.com/about/dashboards#Vulkan)
reports handheld active devices over 28 days ending **2025-11-24**:
1.3 is 26.01%, 1.4 is 0.67%, 1.1 is 62.09%, 1.0.3 is 3.86%, and none is
7.37%. Thus 1.3+ covers 26.68% in that sample. The table has **no separate
1.2 category**, so it cannot estimate the gain for our proposed 1.2 plus
dynamic-rendering target. The 62.09-point 1.1 bucket is only a ceiling on
the extra version coverage from admitting all of it; extension, format,
OS, CPU and RAM checks would reduce that substantially. The dashboard's
page-update date is not its sampling date.

Neither source publishes LSE/RDM population shares. Do not substitute
Qualcomm's shipment share, AnTuTu submissions or `arm64-v8a` share for
ARMv8.2 installed-base coverage. Do not add or multiply these two marginal
datasets to claim a combined gain. A useful maintainer survey would collect
OS, CPU HWCAP, loaded driver/features/formats and RAM together, without
collecting saves or game data.

## Hardware and acceptance needed

There was **no low-end phone available** for this audit and no game/device
run. R07 has zero route pairs; frame medians, spread, image MAE and GPU
phase results are **not measured**. The compiler probes cannot replace
these gates:

- Obtain an API 30/31 arm64 device and an actual Vulkan 1.2 driver exposing
  dynamic rendering. Prefer separate devices/configurations so OS and GPU
  failures can be attributed independently. An emulator can check setup
  and update compatibility, but cannot qualify phone GPU behavior.
- For the CPU change, obtain a non-LSE ARMv8.0 CPU with the other
  requirements satisfied, or isolate the CPU/runtime test from GPU
  qualification. Capture HWCAP, OS/kernel and loaded-library provenance.
- Include a 4–6 GB device with a Vulkan 1.1-class/older mobile GPU for the
  eventual broader target. Check the actual extensions first. Measure peak
  RSS/PSS, GPU heap budget, allocation failures and low-memory kills,
  including BC decoding. Do not describe 4 GB as sufficient yet.
- On private pinned states, run `fh1-race-start-wait` and a free-roam drive,
  retaining its exact input route and seed. The checked-in
  `fh1-free-roam` route provides entry/captures, not a sustained drive.
  Test base and v4, both system and supported custom
  drivers. Retain captures/resolve comparisons, draw counts and GPU phase
  profiles. Use paired, order-balanced routes for cvar comparisons; for
  restart-only builds use phase shares and account for thermal drift.
- Repeat regression routes on the Odin/Astra, test suspend/resume,
  renderer reconfiguration and setup/update flows, then soak the lower-end
  device. Restore the normal APK, settings and device state after testing.

Only after these pass should the manifest, packaging minimums, Java guard,
provenance and player documentation change together. Until then this audit
supports investigation of broader coverage, not a new support promise.

[device layer]: https://github.com/arcanite24/shiftglue-sdk/blob/102fe952422680855291a213cc47a7abfc616ea1/src/ui/vulkan/vulkan_device.cpp
[presenter]: https://github.com/arcanite24/shiftglue-sdk/blob/102fe952422680855291a213cc47a7abfc616ea1/src/ui/vulkan/vulkan_presenter.cpp
[translator features]: https://github.com/arcanite24/shiftglue-sdk/blob/102fe952422680855291a213cc47a7abfc616ea1/src/graphics/pipeline/shader/spirv_translator.cpp
