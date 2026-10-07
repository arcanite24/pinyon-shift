# Development findings and priorities

Consolidated from the development records at `53f9bf9` (2026-09-10) and
updated for the removal of the Xenos renderer (2026-09-28). This is the
current starting point for development, not a release announcement. At `dev`
checkpoint `e5dc399`, the source pins ShiftGlue
`aff6202fcb159721a96d9ce791d280d59703ec9a`; older binary hashes in individual
experiment reports describe those experiments.

Since 2026-10-05, Vulkan is the sole supported graphics API. Direct3D 12 is
legacy and unsupported; new gameplay, performance and release qualification
targets Vulkan. The older shader-pack findings below describe the retained
legacy backend. Current setup and launch behavior is in [Building](BUILDING.md).

## Documentation map

| Need | Read |
| --- | --- |
| Build or recover an installation | [Building](BUILDING.md), [troubleshooting](TROUBLESHOOTING.md) |
| Configure experimental graphics | [Graphics recovery/settings](TROUBLESHOOTING.md) |
| What comes next, in order | [Native port backlog](NATIVE_PORT_BACKLOG.md) (vertical slices NP-0 to NP-14 with sizes, dependencies and gates) |
| How the native renderer replaced Xenos, and what is still open | [Xenos retirement backlog](native-renderer/XENOS_RETIREMENT_BACKLOG.md) (closed; XR-08 and XR-09 keep items that need a person or hardware) |
| What the renderer must implement | [Native frame contract](native-renderer/NATIVE_FRAME_CONTRACT.md), [guest-visible dependencies](native-renderer/GUEST_VISIBLE_RENDER_DEPENDENCIES.md) |
| Current findings and retained changes | This document |
| Performance | [Performance backlog: 4K at 120 fps on Vulkan](PERFORMANCE_BACKLOG.md), [native performance baselines](native-renderer/NATIVE_PERFORMANCE_BASELINES.md), [CPU profiling procedure](native-renderer/CPU_HOTSPOT_PROFILING.md) |
| Previous renderer and performance work | [Research reference](native-renderer/RESEARCH.md): retired plans, journals, failed trials, their Git checkpoints and the [archived Xenos-era documents](native-renderer/RESEARCH.md#archived-xenos-era-documents) |
| Extend the original game UI | [UI API research and implementation tasks](UI_API_PLAN.md) |
| DLC, Rally and the v4 title update | [DLC backlog](DLC_BACKLOG.md), [title update v4 backlog](TITLE_UPDATE_V4_BACKLOG.md) (native Rally and 1000 Club) |
| Produce and validate artifacts | [Artifact production](native-renderer/P1_ARTIFACT_PRODUCTION.md), [shader pack contract](native-renderer/SHADER_PACK_FORMAT.md), [shader capture](native-renderer/CANDIDATE_SHADER_CAPTURE.md), [render tests and diagnostics](native-renderer/FH1_RENDER_TEST_AUTOMATION.md), [manual discovery sessions](native-renderer/DISCOVERY_PLAYTEST.md) |
| Investigate user reports | [September 10 issue review (historical)](https://github.com/arcanite24/pinyon-shift/blob/53f9bf91b470f37cf7efb21c64dc1f8cce50c4c5/docs/GITHUB_ISSUE_TRIAGE_2026-09-10.md) |
| Release behavior and distribution | [Changelog](../CHANGELOG.md), [preview notes](releases/0.1.2-preview.3.md), [legal](LEGAL.md) |

The [renderer research reference](native-renderer/RESEARCH.md) consolidates the
retired replay, provenance, world, vehicle and batching investigations. Exact
historical documents remain accessible through its Git checkpoints, and
documents about machinery removed with the Xenos renderer are kept under
`docs/native-renderer/archive/`. The remaining renderer files describe the
current renderer, formats and procedures; they are not competing roadmaps.

## What the renderer actually does

FH1 CPU code is recompiled. `rexgpu-fh1.dll` runs the FH1 native executor,
the only renderer since `bccf126`: the PM4 command processor consumes the
guest's command stream and the executor runs every draw, clear, resolve and
swap in guest order with the original shaders from a locally produced
offline shader pack. It owns EDRAM surfaces, resolves write the guest texture
layout into the guest-memory GPU mirror, and textures are decoded from that
mirror. No Xenos render target cache or EDRAM emulation is linked
(`e5dc399`). The [frame contract](native-renderer/NATIVE_FRAME_CONTRACT.md)
lists what it covers.

- **Resolution scale:** symmetric 1x, 2x and 3x. Any other scale fails
  graphics setup with an error naming the requested scale; there is no
  fallback renderer. Each scale needs its own shader pack.
- **Shader packs:** shipping builds cannot translate shaders; a draw whose
  shader is missing from the pack is dropped. Each miss is recorded under the
  state's `cache/fh1-shader-misses`, and the next launch's graphics
  preparation sees the new record and produces the pack again with those
  shaders (`96693e9`). A missing shader is therefore dropped at most until
  the next launch. See the [shader pack contract](native-renderer/SHADER_PACK_FORMAT.md#pack-misses-and-self-repair).
- **Guest-visible resolves:** with `readback_resolve = none`, one-off captures
  the game reads on the CPU (for example the car thumbnails it saves) are
  still copied back to guest memory; `fh1_native_readback_new_resolves=false`
  turns that off. `readback_resolve` itself is a developer setting that no
  launcher or default config writes: `full` copies every resolve back
  synchronously (the reference the thumbnail path was checked against, at
  about three times the frame time), `some` and `fast` hand the game the
  previous frame's data (`fast` never reaches free roam). Config migration
  drops it only from files older than schema 24, which older launchers
  wrote for players.
- **Diagnostics:** front-buffer dumps (`fh1_native_dump_frames` /
  `fh1_native_dump_dir`), per-resolve dumps (`fh1_resolve_dump_dir`), the
  frame census (`fh1_frame_census`) and offline frame replays
  (`tools/replay-fh1-frame.py`, `tools/test-fh1-frame-replays.py`); see
  [render tests and diagnostics](native-renderer/FH1_RENDER_TEST_AUTOMATION.md).

Measured before removal, `native` was at frame-time parity with Xenos at 1x
and faster at 2x and 3x on the synchronized routes
([baselines](native-renderer/NATIVE_PERFORMANCE_BASELINES.md)). Those Xenos
comparisons are historical; they cannot be repeated on the current build.
Lower hardware requirements and AMD/Intel qualification remain open.

### Retained changes

The measurements below were taken on the Xenos renderer before its removal;
the changes themselves remain in the shared command processor, texture
cache or title code that the native executor still uses.

- Bulk constant/register writes reduced command-processing overhead. The
  September 4 heavy 2x route reached 57.51 FPS (median of three run medians),
  with 17.390 ms median frame time and 17.241 ms median GPU span. Later heavy
  1x runs measured 15.808–16.426 ms. These are different historical
  workloads, not a current FPS guarantee or a matched Xenia comparison. The
  hash-based execution allowlists of that period were removed in `f6492b7`.
- **Direct reflection-cube import (PERF-05):** changed cubes are written
  directly into the persistent 256×256, six-face, nine-level R10G10B10A2
  texture array with nine compute dispatches instead of a scratch untile and
  54 copies. Median/p95/p99 improved 3.66%/1.42%/6.25%. Default on; control
  `--fh1_direct_reflection_cube_import=false`.
- **One submission per frame (PERF-09):** D3D12 keeps each frame in one
  command-list submission instead of submitting at every PM4 primary-buffer
  end: median/p95/p99 −3.4%/−3.7%/−13.6% at 1x and −7.1%/−8.1%/−15.5% at 2x.
  Control `--d3d12_submit_on_primary_buffer_end=true`.
- **Asynchronous submission (NP-2.6):** a worker thread replays each
  recorded command tape into Direct3D 12, executes it and signals the fence,
  and frames split into a new submission every 1024 draws, so the replay
  overlaps recording instead of running on the GPU commands thread at the
  swap. Race-window median -5.5% and p95 -8% against synchronous submission
  on the same build. Controls `--d3d12_async_submission=false` and
  `--d3d12_submission_split_draws=N` (0 keeps one submission per frame).
- **GPU commands thread bookkeeping (NP-2.7):** per-thread perf counters,
  a reused shared-memory range list, a known-register bitmap on register
  writes and cached sampler parameters. Race-window median 24.3-25.3 ms to
  21.1-21.2 ms on the undisturbed runs of three interleaved pairs. No
  control flag; the changes do not alter rendering.
- **Deadline-driven guest vblank (PERF-14):** replaces polling; −3.20% median
  and −5.60% p95, 62% fewer dropped presents in the measured route. Control
  `--pinyon_shift_fh1_vblank_deadline_wait=false`.
- **Critical-path trace (PERF-11):** default-off
  `--perf_critical_path_trace=true` correlates title emission, PM4
  publication, deferred replay, submission/fence completion, guest vblank and
  present across rotated logs.

Removed with the Xenos renderer (`2f1f1a4` to `e5dc399`): the owned depth,
tile and rectangle clears, the reflection mip replacement, the Carson owned
geometry cache, the tone-map and velocity-dilate replacements and the opt-in
six-family native race pilot. Their documents are
[archived](native-renderer/RESEARCH.md#archived-xenos-era-documents); their
settings no longer exist.

### Rejected and unqualified paths

These were tried on the Xenos renderer, which no longer exists, so none of
them can be re-enabled as written. Keep the lessons; do not repeat an
unchanged failed comparison on the native renderer hoping for a better
result:

- Scaled owned clears, stencil predication, broad handwritten shader
  substitutions, C347/21B70 terrain and two-UV candidates lack retention.
  Foliage, minimap, map, pause, modal and race regressions are explicit gates.
- B848 native vertex specialization was retained at 2x; its 1x extension and
  geometry-ownership experiment failed performance retention. Captured byte
  parity alone did not justify enabling them.
- Geometry containment, buffer recycling, full-tile ownership and 64 KiB
  invalidation experiments remain off. Bounded copy/consumer proofs do not
  establish streaming, mutation, memory or frame-tail benefit. The historical
  largest-containing lookup could redirect a CPU snapshot while a held GPU
  address still named another owner; overlapping ownership must stay consistent.
- The HUD admission prototype is unretained. The 1x comparison had a +28.87%
  acceleration p99; the 2x comparison stopped on green/white glass and headlight
  artifacts. Later stopped controls were never executed.
- The scaled accumulator presentation experiment is finished and archived at
  tag `experiments/scaled-accumulator-presentation-2026-09-01` (`0e0a42b`).
  It failed qualification, is not for merge, and is not a missing production fix.

## Startup correctness: AUD-01 and AUD-02

- AUD-01: queue signaling and event registration check their HRESULTs separately.
  Fence waits recheck completion after stale wakes/timeouts, check device loss,
  and respect worker cancellation. Failed waits propagate to callers without
  retiring pending submissions; shutdown explicitly drains outstanding work.
- AUD-02: prewarm uses the selected pipeline set, saturates the background-worker
  subtraction, and respects CPU/configured worker limits. Empty selections skip
  work without skipping storage finalization. Thread-creation failure uses the
  remaining workers/processor thread; cancellation stops adding work. An empty
  requested set is distinguished from missing requested pipeline hashes.
- Validation: `tools/check-fh1-startup.py` (removed in `f6492b7` with the other
  Xenos-era source checks) compiled the production methods/selection block with
  deterministic failure fakes. Release renderer
  build and installed-AppData startup/shutdown pass (session
  `20260910T224536Z-p3184`, exit 0, one scheduled capture, 452 PSOs created).
  Tested renderer SHA256: `C681D4A4660F08A29C4DCDD88547BA54709E08D868A104CD2336D1063F27162E`.
  No gameplay-performance or full device-loss lifecycle claim is made; AUD-03
  remains separate. Raw evidence is local under `.local/aud-01-02/`.

## Non-renderer findings

| Experiment | Decision and evidence |
| --- | --- |
| Unused main registration translation unit | Exclusion is already in `cmake/PinyonShiftRexGlue.cmake`. Runtime registration uses `PPCFuncMappings`; facade entries remain. About 7.19 MB smaller non-PGO executable in the measured builds, plus compile savings; no demonstrated FPS gain. |
| Import tracing | Keep ON. Six matched stationary runs show no consistent runtime/CPU/tail benefit from OFF. |
| ThinLTO / IPO | Keep OFF. Smaller code, but six stationary runs give inconsistent performance. |
| PGO | Keep OFF. Three-scene training and six held-out race runs produced a 2.02% smaller executable without a consistent runtime win. |
| Guest code, SIMD and compiler flag sweeps | Defer until instruction-level hot-path evidence exists. Helper counts and thread CPU totals are not function costs. |
| Asynchronous/coalesced I/O or lookup caches | Defer. In a warm town window, 161 reads totaled 2.471 ms and 47 open/create calls totaled 5.496 ms. This does not characterize cold disks or unrelated metadata operations. |
| Scheduler/polling changes | Defer. Aggregated guest waits establish completed-call coverage, not critical-path causality or OS ready time. Concurrent waits and completion buckets cannot be added to CPU time. |
| Audio/decompression | Defer without a timed hotspot. Absence of observed XMA stalls does not qualify long-play audio. |

Optional default-off I/O and wait diagnostics are preserved as
[experiment patches](../tools/experiments/README.md), not runtime performance
fixes. Their on/off smoke checks passed; broader save/APC and scheduler behavior
is not inferred from them. Evidence remains under `.local/non-renderer-optimization/`.
Cold storage, OS scheduling traces, lower-spec hardware and long-play NPC/audio
timing remain unqualified. No numerical, memory-order, save or I/O policy change
is justified by these experiments.

## Remaining priorities

1. **User-visible regressions:** capture the reported intermittent green rear
   glass frame, complete sustained Carson town/Hot Hatch Hustle comparisons,
   and verify NPC/title UI animation duration against real time. The older
   area report observed roughly 70 FPS in ordinary driving and 15 FPS near
   houses and wooded hills; its exact location was not established. These
   reports came from the Xenos renderer; recheck them on the native renderer
   before investigating. At 3x a faint green glow on car reflections was seen
   on both renderers before removal. Preserve the failing frame, route,
   settings and actual binary identity.
2. **Clean installation/artifacts:** the packaged-source, SDK-path, pinned
   Python/CMake and build-error logging fixes are in source. Two empty-cache
   NVIDIA 1x startup runs pass, but the fresh 21,735-variant pack is short of
   the developer 22,012-variant pack. Car-selection variants and full gameplay
   remain gates. Graphics preparation now produces and validates the pack for
   the selected scale and repairs it from recorded pack misses (see
   [what the renderer does](#what-the-renderer-actually-does)). Reporter
   confirmation and a fresh disc-to-game installed-launcher run remain
   required.
3. **Artifact lifecycle:** complete selected-scale production, validated reuse,
   cancellation/resume and atomic activation before claiming setup ready.
   Key DXIL by translator, vendor, flags and scale; key device pipeline warmup
   by exact adapter/driver. Keep production separate from compiler-free runtime.
   Qualify 1x/2x/3x and AMD/Intel on actual hardware; NVIDIA results do not qualify
   those vendors. Follow the [P1 gates](native-renderer/P1_ARTIFACT_PRODUCTION.md).
4. **Renderer:** the [Xenos retirement backlog](native-renderer/XENOS_RETIREMENT_BACKLOG.md)
   is closed; the native executor is the only renderer. Two items stay open
   and need what automation cannot supply: an unscripted drive by a person
   (XR-08) and measurements on AMD, Intel and lower-end GPUs (XR-09). Draws
   of a shader missing from the pack are still dropped until the next launch
   repairs the pack. Manual slowdown sites from the September
   discovery playtest — Horizon Outpost entrance and the town plaza (about
   44 ms median, 100–113 ms p95) and a wooded junction near the Gladstone
   Canyon sign (155 ms p95), measured on Xenos — remain useful stress
   locations.

## Validation and evidence

Use [AGENTS.md](../AGENTS.md) for the installed AppData save launch. Never move,
reset or overwrite saves to manufacture a test. Captured commands, shaders,
memory, generated code and binary artifacts stay local.

Freeze source/SDK/settings, pack/catalog and actual binary hashes for each
comparison; embedded metadata has been stale. Validate process/session identity,
input delivery, source/presentation clocks, scene stage, HUD and motion before
comparing frames. Missing captures, abnormal exits and zero candidate admissions
fail the relevant gate. Keep failed attempts with their explanation.

Use the same save, route, scale/output size and scene state for repeated controls
and candidates. Record median/p95/p99, CPU/GPU time, memory, fallback and removed
work. Put screenshots and profiling outside clean timing windows. The historical
Xenia window-change measurements differ from FH1 source-frame FPS and cannot
establish a product speedup. A whole-route median mixes menus and gameplay.

Check changing contents, partial writes, reuse/destruction, in-flight resources,
queries, memory export, fences and history. Small stable shading differences
need an explicit benefit and motion review; missing geometry, flicker, broken
transparency or simulation timing fail qualification. Cover frontend, garage,
day/night driving, traffic, race, rewind, map, pause, photo, FMV and streaming.

Run [contributor checks](../CONTRIBUTING.md) and, for a renderer change, the
golden frame replays (`tools/test-fh1-frame-replays.py`) and the affected
render-test routes. Summarize performance CSVs with
`python tools/summarize-performance.py <session.perf.csv>`. A faithful dependency
replacement can be retained without an FPS gain if it removes proven work
without material regression. Lower hardware claims require measurements on
that hardware. There is no Xenos reference any more: compare with earlier
native runs of the same route and seed. The last build with Xenos is tagged
`xenos-rollback`.

## Historical evidence

Superseded journals and roadmap versions are retained in Git at the source
checkpoint below. Their “next step”, active-goal and staged-binary statements
are historical. Use this document for current decisions and the focused result
documents for reproduction. Local raw evidence directories are not distributed.

Update the relevant finding/checklist in place. Keep one focused result document
when a retained change needs a reproducible contract; put run-by-run logs and
temporary handoffs under `.local`, rather than adding another roadmap version.

| Archived record | Exact checkpoint |
| --- | --- |
| NON RENDERER OPTIMIZATION RESEARCH | [View record](https://github.com/arcanite24/pinyon-shift/blob/53f9bf91b470f37cf7efb21c64dc1f8cce50c4c5/docs/NON_RENDERER_OPTIMIZATION_RESEARCH.md) |
| NON RENDERER OPTIMIZATION RESULTS | [View record](https://github.com/arcanite24/pinyon-shift/blob/53f9bf91b470f37cf7efb21c64dc1f8cce50c4c5/docs/NON_RENDERER_OPTIMIZATION_RESULTS.md) |
| NATIVE RENDERER PERFORMANCE CHECKPOINT 2026-09-04 | [View record](https://github.com/arcanite24/pinyon-shift/blob/53f9bf91b470f37cf7efb21c64dc1f8cce50c4c5/docs/native-renderer/NATIVE_RENDERER_PERFORMANCE_CHECKPOINT_2026-09-04.md) |
| P2 DEPENDENCY RANKING | [View record](https://github.com/arcanite24/pinyon-shift/blob/53f9bf91b470f37cf7efb21c64dc1f8cce50c4c5/docs/native-renderer/P2_DEPENDENCY_RANKING.md) |
| B EPIC EXECUTION | [View record](https://github.com/arcanite24/pinyon-shift/blob/53f9bf91b470f37cf7efb21c64dc1f8cce50c4c5/docs/native-renderer/B_EPIC_EXECUTION.md) |
| NATIVE RENDERER CHECKPOINT 2026-09-10 | [View record](https://github.com/arcanite24/pinyon-shift/blob/53f9bf91b470f37cf7efb21c64dc1f8cce50c4c5/docs/native-renderer/NATIVE_RENDERER_CHECKPOINT_2026-09-10.md) |
| REPRIORITIZED PLAN | [View record](https://github.com/arcanite24/pinyon-shift/blob/53f9bf91b470f37cf7efb21c64dc1f8cce50c4c5/docs/native-renderer/REPRIORITIZED_PLAN.md) |
| NATIVE RENDERER V3 BACKLOG | [View record](https://github.com/arcanite24/pinyon-shift/blob/53f9bf91b470f37cf7efb21c64dc1f8cce50c4c5/docs/native-renderer/NATIVE_RENDERER_V3_BACKLOG.md) |
| NATIVE RENDERER V5 BACKLOG | [View record](https://github.com/arcanite24/pinyon-shift/blob/53f9bf91b470f37cf7efb21c64dc1f8cce50c4c5/docs/native-renderer/NATIVE_RENDERER_V5_BACKLOG.md) |
| NATIVE RENDERER V6 BACKLOG | [View record](https://github.com/arcanite24/pinyon-shift/blob/53f9bf91b470f37cf7efb21c64dc1f8cce50c4c5/docs/native-renderer/NATIVE_RENDERER_V6_BACKLOG.md) |
| NATIVE RENDERER BACKLOG | [View record](https://github.com/arcanite24/pinyon-shift/blob/53f9bf91b470f37cf7efb21c64dc1f8cce50c4c5/docs/native-renderer/NATIVE_RENDERER_BACKLOG.md) |
| XBOX360 NATIVE RENDERER RESEARCH | [View record](https://github.com/arcanite24/pinyon-shift/blob/53f9bf91b470f37cf7efb21c64dc1f8cce50c4c5/docs/native-renderer/XBOX360_NATIVE_RENDERER_RESEARCH.md) |
| PLAYTEST FEEDBACK 2026-09-07 | [View record](https://github.com/arcanite24/pinyon-shift/blob/53f9bf91b470f37cf7efb21c64dc1f8cce50c4c5/docs/native-renderer/PLAYTEST_FEEDBACK_2026-09-07.md) |
| 2026-09-07-area-performance-drop | [View record](https://github.com/arcanite24/pinyon-shift/blob/53f9bf91b470f37cf7efb21c64dc1f8cce50c4c5/docs/native-renderer/screenshots/2026-09-07-area-performance-drop.png) |
| Scene-native, Rayman and performance backlogs, the resource migration checklist and their 2026-09-08–27 journals (`RAYMAN_*`, `SCENE_NATIVE_*`, `PERFORMANCE_*`, `CPU_HOTSPOT_RESULTS_*`, discovery findings, Skate milestones, C1/C2 profile) | [View directory](https://github.com/arcanite24/pinyon-shift/tree/02dfad07fc1236625520a948bb5cd2afe74bfbb3/docs/native-renderer) — resolves once `dev` is pushed; locally `git show 02dfad0:<path>` |
