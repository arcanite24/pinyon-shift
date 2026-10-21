# FH1 native shader pack format

Version 3 is the Forza Horizon 1 runtime renderer input. It stores the
native shader bytecode plus the texture and sampler binding metadata that
ReXGlue normally derives while translating Xenos microcode. A matching entry
therefore bypasses the shader translator completely. The FH1 native
executor, the only renderer, draws every guest draw with the pack's shaders.
Version 3 (NP-9.4) is backend-neutral: the loader is
`rex::graphics::Fh1ShaderPack`, a pack holds DXBC for D3D12 or SPIR-V for
Vulkan, and it carries the host geometry shaders pipelines need, so the
runtime no longer builds them.

This is deliberately title-specific. The runtime looks only for title
`4D5309C9` and selects an exact pack by translator version, backend, device
features, translation flags, and integer render scale:

```text
4D5309C9.fh1-native-v3.<backend>.<features>.<flags>.<scale-x>x<scale-y>.pnsp
```

`<backend>` is `d3d12` or `vulkan`. `<features>` (two hexadecimal digits) holds
the device features that change what the translator emits, in place of
version 2's GPU vendor: for D3D12 only bit 0, switch statements for control
flow, which the translator avoids on Intel. NVIDIA and AMD therefore share a
pack. The producer labels its output with the device it ran on, so keep
`dxbc_switch` at its default while producing.

## Manifest

`tools/native-shader-pack.py` consumes one or more UTF-8 V3 manifests. Multiple
manifests are merged only when their translation configurations are identical;
duplicate identities must contain identical data.

```json
{
  "schema": "pinyon-shift.native-shader-pack.v3",
  "backend": "d3d12",
  "translation": {
    "translator_version": "20260827",
    "device_features": 1,
    "bindless_resources": true,
    "edram_rov": false,
    "gamma_render_target_as_unorm8": false,
    "msaa_2x": true,
    "draw_resolution_scale_x": 2,
    "draw_resolution_scale_y": 2
  },
  "entries": [{
    "stage": "pixel",
    "guest_hash": "0123456789ABCDEF",
    "specialization_mask": "000000000016003F",
    "bytecode": "dxil/pixel.dxil",
    "sha256": "64 hexadecimal digits",
    "texture_bindings": [{
      "bindless_descriptor_index": 0,
      "fetch_constant": 3,
      "dimension": 1,
      "is_signed": 0
    }],
    "sampler_bindings": [{
      "bindless_descriptor_index": 0,
      "fetch_constant": 3,
      "mag_filter": 1,
      "min_filter": 1,
      "mip_filter": 1,
      "aniso_filter": 0
    }],
    "used_texture_mask": 8
  }]
}
```

The stable identity is `(stage, guest_hash, specialization_mask)`. The runtime
never substitutes another specialization. Stages are `vertex`, `pixel` and
`geometry`; a geometry entry has guest hash zero, the backend's geometry
shader key as its specialization and no bindings. Bytecode paths must remain
below the manifest directory, begin with the backend's magic (`DXBC`, or the
SPIR-V word `0x07230203` with a whole number of words), match their SHA-256,
and be at most 16 MiB. Packs are bounded to 65,535 entries and 1 GiB.

An entry may also carry `bytecode_offset` and `bytecode_size`; `bytecode` then
names a file shared by many entries and the entry's bytecode is that byte
range. The shader capture writes this form (`dxil.blob`) because creating one
small file per shader costs about a millisecond each on Windows with real-time
antivirus scanning, which dominated graphics preparation.

Build and verify locally:

```powershell
python .\tools\native-shader-pack.py build `
  .\.local\native-renderer\capture-a\shader-manifest.json `
  .\.local\native-renderer\capture-b\shader-manifest.json `
  --output .\.local\native-renderer\fh1.pnsp
python .\tools\native-shader-pack.py verify `
  .\.local\native-renderer\fh1.pnsp
```

## Binary layout

All integers are unsigned little-endian. A 112-byte header is followed by
88-byte sorted entries and 16-byte-aligned payloads. The header contains magic
`PNYNSHPK`, version `3`, sizes and offsets, entry count, payload size, a SHA-256
of the complete index and payload, translator version, backend (1 D3D12, 2
Vulkan), device features, translation flags, render scales, and two zero
reserved words.

Each entry stores stage (1 vertex, 2 pixel, 3 geometry), bytecode format
(equal to the backend), guest hash, specialization mask,
payload offset and bytecode size, texture/sampler counts, used-texture mask, a
zero reserved word, and bytecode SHA-256. Its payload is bytecode followed by
16-byte texture bindings and 24-byte sampler bindings.

The producer and runtime independently validate configuration, sizes, ranges,
alignment, hashes, binding bounds, texture masks, sorted uniqueness, and
consistent layouts across specializations before exposing bytecode.

## Runtime gate

`PipelineCache::TranslateAnalyzedShader` first performs the exact pack lookup.
On a hit it installs bytecode and bindings and continues through normal root
signature and pipeline creation without Xenos shader translation. During
explicit offline corpus production, a miss may use the compatibility translator
and is observable by the capture callback.

Geometry shaders (point sprites, rectangle and quad lists) come from the pack
too: `PipelineCache::GetGeometryShader` looks the key up, and the DXBC
geometry shader generator and `DXBCChecksum.cpp` are compiled only into the
producer. For every vertex shader translation it captures, the producer also
writes the geometry shaders pipelines drawn with it can take (rectangle and
quad lists without point data, point lists with and without point
coordinates), so the finite set follows the pack's vertex shaders. A runtime
geometry shader miss is logged, recorded like a shader miss and the pipeline
is not created.

Normal FH1 execution always enforces this gate; there is no runtime
setting or launcher argument that can disable it. A miss is marked
terminal-invalid and reported as a GPU error before the translator can run,
and the draw that needed it is dropped.
The normal `rexgpu-fh1.dll` is compiled without the DXBC shader compiler.
Translation exists only in the explicit, unstaged `rexgpu-fh1-producer.dll`
target used with the locally extracted disc corpus. `launch-preview.ps1`
temporarily stages that producer only for a `-DiscShaderCorpusDir` run and
removes it afterward. The FH1 runtime is fixed to native host render targets,
so the alternate ROV shader ABI and its synthetic depth shader are absent too.
`tools/run-fh1-render-test.py
--require-zero-shader-misses` independently requires a zero-entry capture
summary, so tests prove both that the runtime did not fall back and that the
expected scene completed.

Packs are produced per integer scale (1x to 4x) and must be produced with the native renderer: a pack
produced with the removed Xenos renderer lacked the native depth-rectangle
clear vertex shader `1E6883FCCDE1F688` (`79e072a`).

## Vulkan packs

The Vulkan runtime keeps its SPIR-V translator, so a Vulkan pack only
saves translation time (NP-12.6): `VulkanPipelineCache` looks each
translation up in
`4D5309C9.fh1-native-v3.vulkan.<features>.<flags>.<scale>.pnsp` first
and translates misses as before, logging the first 64 with the hit count.
`<features>` is a hash of what the SPIR-V translator's output depends on
(the device's SPIR-V version and storage buffer range, its shader features,
2x MSAA without attachments); `<flags>` are the manifest flags (EDRAM
through fragment shader interlock, 8-bit gamma, native 2x MSAA).

Every translation is also sent to the shader translation observer, so a
pack comes from any Vulkan session with a capture:

```powershell
python .\tools\run-fh1-render-test.py .\config\render-tests\fh1-race-sync.fh1test `
  --state-root <seed> --output <out> --build-directory <vulkan build> `
  --shader-capture-dir .\.local\vk-capture --game-argument=--gpu_backend=vulkan
python .\tools\native-shader-pack.py build .\.local\vk-capture\shader-manifest.json `
  --output .\.local\vk.pnsp
```

A later session's capture adds its misses. A pack captured from
`fh1-race-sync` on the RTX 4080 held 479 shaders; `fh1-buy-car` then hit
377 and translated only the showroom's new ones.

## Frame inspector diagnostics

The desktop [frame inspector](FRAME_INSPECTOR.md) previews a live frame or a
replayed dump without changing the shader-pack format. Its preview compute
shader and overdraw fragment shader are host diagnostics, compiled on demand;
they are not guest translations and are not exported into packs. Diagnostic
pipeline state has its own pipeline-description key and cache version, so a
wireframe or overdraw pipeline cannot be reused for ordinary rendering.
Diagnostic pipelines are not added to the persisted pipeline descriptions.

## Pack misses and self-repair

The title generates some shaders at runtime (disc shaders it patches with
vertex fetches for other layouts, relinked exports) on screens the
preparation route, `fh1-shader-preparation` from an empty profile, never
reaches. A shipping build records each such miss once per session: the
guest microcode is written as `<stage>-<hash>-<modification>.bin` (for
example `vertex-37EBBE47900A46F5-0000000000000007.bin`) under the state's
`cache/fh1-shader-misses` (SDK `3986ece`). A geometry shader miss is an empty
`geometry-0000000000000000-<key>.bin`; the producer builds that key.

Graphics preparation (`tools/prepare-fh1-shaders.ps1`, run by
`launch-preview.ps1` and the launcher) includes the hashes of those records
in its preparation key. A new record therefore makes the next launch prepare
the pack again, passing the directory to `produce-fh1-artifacts.ps1
-ShaderMissDir`; the producer translates every recorded pair after the disc
corpus (`96693e9`). A shader missing from the pack is dropped only until the
next launch. Two rounds from recorded misses took `fh1-race-sync`,
`fh1-buy-car` and `fh1-rewind-sync` to zero pack misses. The records are
game-derived microcode and stay in the local state like the pack.

The preparation route runs on wall-clock time (`# clock-hz 60`), so how far
the game gets between its scripted presses depends on the machine. The
producer run translates and compiles as it goes, while the compiler-free
check runs from the finished pack, so on a slow machine (issue #316: an Intel
HD 520 laptop with a two-core i5-6300U) the check can reach shader variants
the producer run never drew. Graphics preparation therefore passes
`-AllowShaderMisses`: such misses become a warning that counts them by stage
and lists the first ones, and `production.json` records them under
`shader_misses`. The game handles them like any other pack miss. A crash, a
route that does not complete, a native executor that drew nothing and a pack
that did not load stay fatal. Each fatal error names the route's result,
exit code and runtime log, which `setup-error.json` also records
(`build_log`, `exit_code`, `output_tail`). Production without the switch
still requires zero misses. Each route launch's hang guard is
`-RouteTimeoutSeconds` (1800 s by default; it was 600 s and covers startup and
the disc corpus translation as well as the route).

## Public-source boundary

Extracted guest shaders, translated bytecode, manifests containing guest shader
identities, and completed packs are locally derived artifacts; they must remain under `.local`.
Repository policy continues to forbid `.dxil`, `.dxbc`, and
`.pnsp`. The public repository contains the format, producer, loader, and tests.
The pack does not enable guest draw or resolve suppression.

## Qualification history

These qualifications were run while the Xenos renderer still drew most of
the frame; the gate itself is unchanged, but their frame rates are
historical measurements from before its removal.

The initial `.xsh` / `.xpso` proof produced 721-entry packs at every supported
integer scale. The asset-derived producer supersedes those observed-cache packs.
The table below records the September 4 qualification. The developer's
installed 1x NVIDIA pack, produced 2026-09-21 and verified on 2026-09-27, has
24,763 entries (530,928,192 bytes, content SHA-256
`7DE1D7AC973399CBD30EB164B2C535A8E91F7F9617AD1411A04EF2AC1F63CE85`).
The September 4 NVIDIA packs were:

| Scale | Entries | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| 1x | 22,012 | 468,825,976 | `1636179BF8633D7406C7C3C735DD600C0C05666D8A8A8CAC188433730A38C026` |
| 2x | 22,012 | 473,489,272 | `D6E62162510BE0EDFC0CA4D1624B498F51024F7BC5AC2597A23C37929E030A3E` |
| 3x | 22,012 | 473,489,272 | `53288ADF3C958C994D857CC2DEEF8877A0EA1DF4E3B89207B7E6AF18778C83B0` |

That pack passed unattended 2560x1440 race, free-roam, SELECT-map, pause/resume,
photo-mode, and combined HFR mode tests with zero runtime shader translations.
The strict HFR session `20260904T043852Z-p44060` produced 73.426 source
frames/s, zero duplicate presents, and title time at 1.004x wall time. A
negative run without the pack was rejected by the runtime gate, proving that
strict mode cannot silently invoke the compatibility translator.

Strict 1x HFR session `20260904T044521Z-p45072` also completed the combined
mode route with zero misses and duplicate presents. Capture-light strict 3x
session `20260904T045529Z-p556` rendered a true 3840x2160 world frame with zero
misses, 75.066 source frames/s, 74.860 presents/s, zero duplicate presents,
and title time at 0.995x wall time. These captures do not qualify moving-car
rendering: subsequent gameplay reproduced severe 3x vehicle glow. Other GPU
vendors also remain unproven.

`tools/extract-fh1-shader-corpus.py` reads loose assets, FH1's LZX track
archives, and the locally loaded `default.xex` image. The executable contains
additional programs and vertex declarations needed by the map and motion
passes; omitting them caused a blank SELECT map and smeared moving cars at 1x.
The current supported dump yields 3,819 raw programs in 4,770 containers and
12,846 programs including locally derived vertex variants. Use
`config/render-tests/fh1-moving-map.fh1test` with a free-roam save to check
moving vehicles and the map; startup-only qualification is insufficient.

At 2x, automated corpus session `20260904T055222Z-p28564` translated 9,600
vertex and 12,098 pixel specializations with zero failures. The merged pack has
21,984 entries, is 472,656,904 bytes, and has SHA-256
`572CDA43FEAF4B98B77B850034E28C54D67D95DEE8B942E9D2050CF605897C7F`.
Strict session `20260904T055452Z-p33360` used that pack without an `.xsh` seed,
captured zero misses, rendered 86.478 unique source frames/s, emitted no
duplicate presents, and kept title time at 1.007x wall time.

The corresponding strict no-seed 1x session `20260904T060200Z-p47700`
captured zero misses at 1280x720, produced 87.904 source frames/s, and kept
title time at 1.006x wall time. Strict 3x session
`20260904T060433Z-p11356` captured zero misses at 3840x2160, produced 75.343
source frames/s with zero duplicate presents, and kept title time at 0.996x
wall time. `tools/launch-preview.ps1` now verifies and stages the matching
local scale pack for ordinary runs and enables the strict no-translation gate.

Ordinary launches also stage the FH1-only startup catalog from
`.local/native-renderer/fh1-native-prewarm/cache` when present. It contains the
read-only `fh1-native-shaders-v2.bin`, `fh1-native-pipelines-v1.bin`, and
`fh1-gpu-prewarm-v3.txt` allowlist; all three files are required and verified
by SHA-256 while staging. `build-fh1-gpu-prewarm.py --legacy-cache` converts the
last qualified ReXGlue capture into those native startup inputs. Graphics
production passes `--all-stored-pipelines`: since the native executor became
the only renderer the GPU execution corpus names no pipelines, so the
allowlist is every pipeline the preparation route created (379 at 1x on
2026-09-28; preparations between `bccf126` and `b59061f` wrote an empty
allowlist and created every pipeline during play). The v2 shader
catalog stores each FH1 shader's raw identity plus the constant maps, vertex
binding strides, output masks, register requirements and memory-export facts
that drawing still needs. Each bounded record has its own XXH3 checksum and the
runtime requires a sorted, unique, exact-EOF catalog. Parsed instructions,
disassembly, labels and translator-only control-flow analysis are not stored.
Normal runs therefore neither execute `AnalyzeUcode` nor open or mutate
`.xsh`/`.xpso` stores. These remain local game-derived artifacts. The
current qualified catalog contains 461 pipeline hashes, 73,781 draw identities
and 690 copy identities.

Schema 21 makes the FH1 native route unconditional and removes its former V4
enable/disable setting. Strict session `20260904T070431Z-p24828` verified the
combined HFR/UI route after migration with zero shader translations, zero
synchronous pipeline creations and zero prewarm fallback draws.

The separate precompiled-shader CVar is also retired. Normal FH1 execution now
rejects pack misses structurally; only the local, observer-backed disc-corpus
producer may execute the translator. Positive session
`20260904T070857Z-p34300` passed the complete combined route with zero runtime
translations and zero synchronous pipeline creation. A no-pack negative smoke
session `20260904T071055Z-p35632` failed on explicit precompiled misses while
recording zero translated shaders, proving direct launches cannot fall back.

The completed v2 analysis catalog contains 11,628 unique guest shaders
(8,409,800 bytes, SHA-256
`09F6FDC0FBD9961BA000A2B30B3839FA9D4BA0292D09F7FA436EC4B761D0613E`).
It unions the complete disc corpus, the finite generated/system title seed,
and runtime-generated car-selection programs found by the deterministic race
route. Shipping sessions at all three scales then completed the full event and
race with zero shader misses. The binary gate additionally requires
`AnalyzeUcode` to be absent from the runtime and present only in the offline
producer.
