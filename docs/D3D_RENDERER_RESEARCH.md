# D3D-level renderer research

Status: closed 2026-10-15. Every item ran to its gate. DL-0.1 passed, DL-0.2
found the recording brackets, DL-1.1 landed on its gate (ceiling about 3 ms a
frame net on the Odin) and the maintainer chose to go on; DL-1.2 passed on the
desktop; DL-2.1 failed twice (exact, decoder up to -0.8 ms, process CPU
flat); DL-2.2 as designed was not built, because no race list draw is culled
per tile; DL-3's gates failed on the desktop and the Deck (process CPU about
-0.9 ms against -3). The shader cache that came out of DL-2.1 (DL-0.3
revisited) landed at its gate and is on by default at the maintainer's choice.
The rest of the code stays in the tree, off by default.

The near-native plan ([NEAR_NATIVE_RESEARCH.md](NEAR_NATIVE_RESEARCH.md))
ended with the GPU front end as the largest pool left on the Odin: the guest
builds Xenos command buffers, the host decodes them (about 9 ms a frame),
submits (2.7 ms) and records. Every attempt to make that layer cheaper from
the inside failed (G0, NN-2.2, NN-2.6). This page asks whether to replace
the layer: take the game at its Direct3D calls and drive Vulkan from them,
instead of emulating the GPU at the PM4 packet level.

Item prefix: DL-. Detailed notes, with addresses and run folders, are in
`.local/backlog-research/d3d-renderer-2026-10-14/` (01 prior work and
architecture, 02 the guest D3D seam, 03 prior art, 04 cost ceiling and
gates). Reverse-engineering results are recorded in
`site/findings/rendering.toml`, group "D3D inside the game".

## Answer in short

- **A pure draw-call renderer does not fit FH1.** Most of the scene does
  not go through draw calls. It arrives as prebuilt D3D command buffers
  (display lists, PM4 inside), some streamed in from asset files and some
  recorded by the track ahead of time. This is why the project's earlier
  native renderer moved to decoded PM4, and why NEAR_NATIVE rejected
  "D3D draw-call HLE only (UnleashedRecomp's route)".
- **A hybrid could fit:** draw calls taken at the engine's own device class,
  plus a **list compiler** that translates each display list once and
  replays the translation, keyed on the list and its *fixups*. New in this
  research: the lists are not re-recorded every frame. D3D patches
  per-object textures, streams and constants into fixed slots before each
  run. That explains why NN-0.10 found lists both repeating byte for byte
  and being rewritten. It also means a compiler keyed on (list, fixup
  values) need not hash bytes, which is what made G0 and the recorder
  replays slower.
- **Ceiling on the Odin: about 2-5 ms of CPU a frame realistically**, 6-9.5
  ms at best, nothing at worst, out of about 13.7 ms on the GPU path today.
  The deciding unknown is the **fallback share**: draws whose bytes reach
  the GPU through a path the renderer cannot see, which would still need
  the PM4 decoder. GPU time saves only 0.2-0.6 ms, so the GPU cannot justify
  the project. Desktop would save an estimated 4-8 ms and the Deck 7-15 ms,
  where it would show as power, since the Deck is GPU and power bound.
- **The closest precedent is CoD3Recomp** (a ReXGlue port of Call of Duty 3).
  It records command buffers on four threads, replays them under predicated
  tiling and copies its own pre-built state packets into them, much as FH1
  does. It keeps a small non-executing packet reader at record time and
  doubled its frame rate in one scene.
- **DL-0.1 passed (2026-10-14):** 9.5-16 % of drawn draws would need the
  fallback on the Odin and 5-16 % on the desktop, and the visible draws
  carry about 10 ms of decoder and submission time a frame.
- **DL-1.1 is at its gate, not past it (2026-10-14):** with the PM4 path
  doing no work for the visible draws, Odin process CPU fell 6.28 ± 0.42 ms
  against a 6.17 ms gate, about 3 ms a frame net of the native draw cost.
  That is the ceiling of the whole renderer on the Odin, before fidelity.
- **Original recommendation: run DL-0.1, the source census, before any design work.**
  It is a probe build of default-off hooks. Go only if the fallback share is
  30 % or less and the draws a hybrid can see carry at least 6 ms of
  decoder and submission time a frame.

## What is native today and what is still Xenos

The renderer is already "native" in places. The FH1 native executor owns
EDRAM, clears, resolves, the swap and the guest-visible side effects. Still
Xenos emulation:

- the PM4 decode;
- the register file;
- deriving each draw's state from registers (about 20 steps, about 980 ns a
  draw on desktop);
- the 512 MB guest-memory mirror;
- the tiled texture cache;
- a shader ABI that reads Xenos registers.

On Vulkan the old render-target cache is still built as a fallback.

Attempts to reuse repeated work at this layer all measured slower or below
their bars:

| Attempt | Result |
| --- | --- |
| Per-draw templates | 1,205 against 1,115 ns a draw |
| Buffer replay | 1,571 against 1,472 ns a draw |
| Segment replay | recorder 0.3 % faster |
| Constants by address (NL-3.3) | recorder 7.85-8.49 against 7.47-7.72 ms |
| Native draw ABI (NP-9.5) | about a sixth of one thread at most, not built |
| G0 replay probe (NN-0.10) | -2.54 ms of process CPU against a 6 ms bar |

The common cause: checking that a draw is still valid cost about as much as
deriving it, and nearly every draw brings new shader constants. A D3D-level
renderer avoids the check only where the API says what changed. That is
true for draw calls and for list fixups, and false for list bytes written
any other way.

What a D3D-level renderer must still provide to the game:

- the fence words the title polls, the InsertCallback wait and interrupt
  handshake (about 12 waits a frame), vblank and the ring read pointer;
- the car thumbnail and other resolves the CPU reads;
- the resolve chains the HDR image depends on;
- EDRAM aliasing between formats;
- per-band culling under tiling;
- about 20 MB of CPU-written vertex and index data a frame;
- occlusion queries while loading.

The game never uses memory export.

Reusable as they are:

- the shader translator and shader packs;
- texture decode;
- the pipeline cache;
- the executor's surface and resolve code;
- the presenter;
- the render-test tooling.

## How FH1 reaches the GPU

Details and addresses: findings "engine graphics device class", "D3D
command-buffer fixups", "command buffers from assets and run-time
recording", "D3D command buffers", "D3D draw entry points".

- D3D9 from XDK 2.0.21119 is linked into the executable, in two code bands.
  72 functions write PM4 headers, all D3D. The engine itself writes no PM4
  and no GPU register.
- **The engine draws through its own virtual class `CD3D9GraphicsDevice`**
  (67 slots). Its draw slots reach every known D3D draw entry point, so one
  vtable hook sees every immediate draw, with the state calls before it.
  Most D3D state setters are inlined into the engine as stores plus dirty
  bits, so there is no SetRenderState function to hook below this class.
- **Display lists** run through `D3DDevice_RunCommandBuffer` (542 a
  presented frame). Before each run the owner applies the object's dynamic
  fixups through D3D's fixup dispatcher, one setter per resource type.
- **Origins:** lists come from asset files (models, with static and dynamic
  fixup tables), from run-time recording (track zones, within a time and
  fixup budget), and possibly from cloning.
- **Tiling:** D3D's worker replays the tiling stream once per tile. At the
  API level each logical draw is seen once, with its bin mask, and the
  renderer must apply the game's per-band culling itself.

**Coverage, as an estimate.** About 610 immediate draw calls and 542 list
runs per presented frame (desktop probe, route average). Drawn race draws
are estimated at 55-65 % from lists and 35-45 % from immediate calls
(bounds 40 % and 75 % for lists). The swing depends on whether the two main
draw entry points (`82416380`, `82415F68`, about 540 calls a frame) write
into ring segments or into lists being recorded. The earlier "42 draws a
frame through D3D" count covered only the `8240F4D8` wrapper, so the two
numbers do not conflict.

## Prior art

| Project | Layer intercepted | How it handles the hard parts | Result |
| --- | --- | --- | --- |
| Unleashed Recompiled (Sonic Unleashed, 360) | D3D device replaced, about 40 functions; inlined setters caught by the device layout and dirty flags | no EDRAM model, no tiling; resolves alias the render target until a copy is needed | no published performance numbers |
| Marathon Recompiled (Sonic 06) | Unleashed's renderer | tiling forced off by making the game's surface-size check return 0 | FH1's own non-tiled path drops the static world, so this does not carry over |
| CoD3Recomp (ReXGlue) | D3D device, plus a non-executing reader for the packets the game copies into its lists | lists recorded on four threads, replayed per predication mask | 0 mismatches in about 390,000 draws per 5 s; 91 to 182 fps in one scene |
| Deadly Premonition (ReXGlue) | D3D device; command stream dropped unparsed | EDRAM aliasing added back by hand; most bugs in the shader translator | 5.1-6.1 ms CPU a frame at 60 fps (RTX 5070, 2x) |
| Downpour attempt (ReXGlue) | above the device layer, then a hybrid over the emulated GPU | missed draws; buffers freed while in use | abandoned as a dead end |
| Cxbx-Reloaded (original Xbox) | D3D8 patches, plus a push-buffer interpreter for games that run push buffers | had to add the interpreter | 16 % of 1,032 titles playable |
| Xenia, RPCS3, Dolphin | hardware commands | the D3D library is compiled into each 360 game, so there is no shared API | |

Failure modes others reported:

- hooking above the device layer;
- trusting device state the game overwrites with its own packets;
- dropping EDRAM aliasing;
- shader translation bugs;
- drawing on top of the emulated GPU;
- freeing buffers queued work still uses;
- hook cost while off (measure p90 and p99, not the median);
- per-game effort: none of these renderers is reusable across games.

## Cost ceiling (Odin race, base build, rows 4300-6900, about 1,890 drawn draws a frame)

| Part | ms a frame | M instructions a frame |
| --- | ---: | ---: |
| PM4 decoder thread (decodes and records Vulkan inline) | 7.3-9.9 | 42-63 |
| GPU submission thread | 2.6-3.0 | 6-8 |
| Guest render thread | 4.3-4.9 | 11-14 |
| of which guest D3D code (estimate, with two helper threads) | 0.8-0.9 | |
| Write-watch protects and faults | about 0.5 | |
| Everything else | 17-21 | |

Inside the decoder, the per-draw work is 4.1-4.8 ms (constants about 1.4),
PM4 parsing about 2.7 ms and shader-hash reloads about 0.9 ms.

A D3D-level renderer:

- **Removes:** PM4 parsing for the draws it sees, the Xenos-specific state
  derivation (an estimated 1.4-1.9 ms), the tile replays and most of the
  write-watch work. The shader rehash can be fixed on its own, without this
  project (DL-0.3).
- **Keeps:** about 60 % of today's per-draw cost (pipelines, constants,
  descriptors and the draw itself, about 1.6-1.8 µs a drawn draw) and the
  driver's command emission on the submission thread (2.0-2.8 ms).
- **Adds:** state capture on the render thread, which roughly cancels the
  guest D3D code it replaces, and the fixed cost of a PM4 fallback.

| Fallback share | Odin CPU saved a frame (estimate) |
| --- | --- |
| 10 % or less | 6-9.5 ms (best case) |
| 30-60 % | 2-5 ms (realistic) |
| over 70 % | nothing, or a loss |

A cross-check against G0's measured replay agrees: about 4.1-4.9 µs net
per converted draw.

## Design if the gates pass

- **Seam:** the `CD3D9GraphicsDevice` vtable for immediate draws, state,
  resources, resolves and present. `RunCommandBuffer`, the fixup
  dispatchers and the list loaders for display lists.
- **List compiler:** translate a list's PM4 once, when it is loaded or
  recorded, into host draws with its fixup slots as host bindings. Replay
  the translation at each run with the caller's inherited state. Key it on
  the list and its fixups; any other write to a list invalidates the
  translation.
- **Packet reader:** a CoD3-style reader at record time, which executes
  nothing, for the state packets the game copies into lists.
- **Tiling:** replay each logical draw once per band with that band's
  scissor and the game's per-band culling. There is no 10 MB EDRAM limit on
  the host, so the render target is full size.
- **Kept:** shader translation, texture decode, the executor's surfaces,
  resolves and presenter, and the guest-visible fence and interrupt
  protocol.
- **Fallback:** draws from a path the renderer cannot see keep the PM4
  decoder, with an explicit count. A hybrid drawing on top of the emulated
  GPU was a dead end for Downpour, so the fallback must hand whole passes or
  frames to the decoder, not single draws.

LEGAL.md allows this: it is interface-level host code written from our own
analysis, and the shader translation stays generated.

## Items

| Item | What | Gate | Size |
| --- | --- | --- | --- |
| DL-0.1 | **Source census** (probe build, default-off hooks, no behaviour change). Entry hooks on the draw entry points log whether the device writes into the ring, a list being recorded or the tiling stream. Count calls per vtable slot. Trace each list's life through RunCommandBuffer, the fixup dispatchers, the file loader and the clone path. Classify every write into a list as fixup, stream load, clone or other. In the decoder, tag every drawn draw by the class of its bytes, and time the decoder and the guest D3D functions by class. Routes: race (tiled desktop, untiled Odin), map, car select. | Go if "other" writes to lists are 0, the fallback share is 30 % or less, and the visible draws carry at least 6 ms of decoder plus submission time on the Odin. 30-50 % fallback: only with the list compiler. No-go above 50 % or under 4 ms. | S-M |
| DL-0.2 | **Find the recording brackets**: BeginCommandBuffer, EndCommandBuffer and BeginTiling, by watching the device's write pointer for one frame. The async command-buffer path (`829EC928`): how many lists it runs and where it fixes them up. | Needed for DL-0.1's attribution | S |
| DL-0.3 | **Shader-hash reload fix** inside today's decoder (about 0.9 ms a frame), independent of the rest | in-run A/B, decoder CPU -0.5 ms | S |
| DL-1.1 | **Wrong-image ceiling**: skip decode and recording for the draws DL-0.1 marks visible, toggled in-run | process CPU drop of at least (visible draws × 2.2 µs) + 3 ms, about -6 to -7 ms | S |
| DL-1.2 | **Fidelity pilot**: the HUD pass (about 42 draws, about 0.2 ms) through the new path, against captures. Below noise as a cost gate. | captures within A/A; no frame-time tail change | M |
| DL-2.1 | **First native slice**: immediate draws of one self-contained pass (car or vegetation lists), with the list compiler for its lists | at least -3 ms in-run on three pooled runs; decoder instructions per draw -30 %; p99 no worse; captures within A/A | L |
| DL-2.2 | **Tiling at the API level** for that slice: replay per band with the game's per-band culling | same captures, untile counters at 0 for the slice | M |
| DL-3 | **Whole frame**: every pass, the PM4 decoder kept only as an explicit fallback | DL-2's gates on the whole race, the Deck and desktop; GPU wins count only if KGSL busy falls by 2 SE pooled | XL |

## Measurement method

As NEAR_NATIVE:

- CPU results are judged in-run only: drawn draws swing 753-1,859 between
  runs, which moves raw instructions by 20 %.
- In-run window means are adjusted for draw count: the toggles fall on the
  same route frames in every run, so one side can carry a heavier scene
  phase (DL-0.3 saw 170-590 more draws in every memo-on window). An A/A on
  the same route shows the bias.
- One in-run A/B resolves about ±0.9 ms.
- Cross-build per-thread instructions spread 1.1-4.9 %.
- p90 and p99 frame times are checked as well as means.
- Device runs use private state roots and pinned seeds.

## Risks and open questions

- The fallback share is unknown until DL-0.1. If `82416380` and `82415F68`
  record into lists every frame, a record-time translation pays every frame
  too, and the project shrinks toward NN-2.3.
- The resource-type numbering of the fixup dispatcher is assumed from the
  XDK and is checked only for textures and command buffers.
- The v4 image shares the runtime (every seam function maps at a constant
  offset per band, two unverified), but the v4 vtable addresses need the v4
  image.
- Per-game effort is large: no 360 D3D-level renderer is reusable, and each
  project re-found its own addresses.
- Shader translation bugs dominated other projects' visual bugs. Ours is
  mature, but its ABI reads Xenos registers and would need a new constant
  layout.

## Progress

| Item | Outcome | Evidence |
| --- | --- | --- |
| NA-3.1 (#754, epic #757) | **Rejected 2026-10-20.** Its prerequisite NA-2.4 was rejected on cost. DGC is unavailable on the Odin (Turnip V37) and binds compute pipelines only on the Deck (RADV 24.3-devel, CS-0.3), so the stage gate's Odin and Deck frame A/B cannot run. Ceiling on NVIDIA: the pilot pass's whole CPU cost, 126-190 program draws a frame at 650-960 ns complete cost (NA-2.4 mode 4), is 0.08-0.18 ms a frame, below the in-run frame resolution (±0.6 ms), and DGC would replace only the recording part of it. |
| NA-3.2 (#755, epic #757) | **Rejected 2026-10-20.** Resolves: the pilot pass contains no resolves or copies. Geometry ceiling: `gpu_d3d_program_probe` (2 skips the draw commands inside the marked lists, 1 draws their first triangle) with `gpu_d3d_program` 4 and `fh1_native_gpu_profile`, toggled 0/2 every 60 frames on the Odin v4 drive with 30-frame GPU windows; each probe-2 window against the mean of its probe-0 neighbours, two runs: 0.37 ± 0.22 and 0.22 ± 0.23 ms saved of 11.3-11.9 ms labelled GPU time (main scene pass 7.1 and 6.4 ms). The whole-frame GPU span stays at the 16.7 ms frame period and cannot resolve it; 300-frame windows were confounded by the scene (main pass sd 2.1 ms). Native vertex input could save only part of that ceiling. |
| NA-3.3 (#756, epic #757) | **Expansion rejected 2026-10-20.** Root from an Odin call-graph profile: `sub_82DFC570` (2.1 % inclusive; `82DE3058` under 0.3 %). Region: 77 members, 2.5 MB generated source; generator fix for the indirect-call binding. Oracle: 129,232 checks, all stopped at the first visible store, no difference. Per call: multivac -2.6/-8.6/-9.1 %, Odin +12.5 % (20,134 against 22,647 ns). Odin frame A/B (0/1 every 150 frames, two runs): frame +0.08 ± 0.08 ms, process CPU -1.5 ± 0.9 and -0.3 ± 0.9 ms. Two of five call-alternating runs failed the drive-start movement check; not investigated. Data ownership and explicit FP not built: the region is already bit-exact and the subtree is about 0.9 ms a frame of off-path thread time. |
| Survey item 2 (#784) | **Rejected 2026-10-21.** Culling invisible main-world objects before the guest builds their draws, after Skate3recomp. Census (`fh1_visibility_census`: an occlusion query around each draw of one frame in N, in draw order) over the frame-base drive: main-scene depth-writing draws that pass no samples, multivac (untiled) 48.3 % of 1,400 a frame (42.4 % of vertices), shadow depth 38.0 % of 773; Odin 59.9 % of 914 late-depth and 70.2 % of 438 early-depth draws (39.7 % and 66.7 % of vertices). With the depth test off on census frames (`fh1_visibility_census_no_depth`): multivac 16.8 %, Odin 31.0 % and 15.2 %. Ceiling probe `fh1_visibility_oracle_skip` (renders wrong: drops a draw before its derivation when the same shaders, index range, count, targets and ordinal passed no samples at the last census; census every 8 frames, toggled every 60 frames, each window against its neighbours): multivac frame -0.72 ± 0.51 ms, decoder -0.71, submission -0.76, GPU -0.45 ± 0.45 ms; Odin main pass -2.16 ± 0.45 and -3.15 ± 0.58 ms of 7.8-8.8 ms, process CPU -1.2 ± 0.8 and -1.8 ± 0.5 ms, decoder -0.6 and -0.8 ms. Dropping only late-depth draws kept 1.6-1.7 ms of it, so the cost is vertex and binning work, not shading. Off-screen population only (oracle fed by the no-depth census): Odin main pass -0.64 ± 0.77 and -1.44 ± 0.52 ms, process CPU -1.4 ± 1.2 and -1.5 ± 1.1 ms, decoder within noise. A frustum test against conservative bounds would catch less than that; the world draws are in world space (camera matrix at c128-c131), but bounds would need each mesh decoded and its writes tracked, and the static-world transforms did not match the authored spatial catalog (see Reverse engineering > World). The occluded rest needs this frame's depth (or old depth, which pops), so neither was built. Probes kept, off. |
| NA-2.3/2.4 (#752, #753, epic #757) | **Correct, rejected on cost 2026-10-20; code off.** Pilot pass: the procedural-model (vegetation) lists from the NA-2.2 census. Game side (`src/native_renderer/d3d_program.cpp`): hooks at the owner's two calls into the list runner (base `82418A24`/`82418EC8`, v4 `824489D4`/`82448E78`, plus the instruction after each) set a thread flag, and the runner entry (base census hook `82416A00`, v4 `824469B0`) marks the buffers of the list it runs in `rex::system::d3d_program`. Decoder: an indirect buffer at trace depth 2 or more that is marked is bracketed with `DrawProgramBegin/End` record calls. Vulkan backend (`vulkan_draw_program.cpp`, `gpu_d3d_program`: 0 off, 1 shadow, 2 performance, 3 record and count): one program per (buffer, entry state hash, entry shaders), a draw is a hit while its state hash, active shaders, primitive type, index count, draw initiator, DMA range, resolution scale, HUD settings, object slot and index version are unchanged; a hit skips shader analysis, primitive processing, translation, the pipeline memo (same render pass) and the viewport memo. NA-2.3: an indexed draw's guest index range is copied into a 16 MB device-local arena (watch first, then request, then copy), the version is retired when a CPU or GPU write fires its watch and freed once the completed submission passes its last reader; no arena fence. Desktop race (`fh1-race-sustained`, appdata-2026-09-27 seed): shadow 4,624,109 draws compared, 0 mismatches, 0 index mismatches, route passes; performance mode 99.1-100 % hits, derivation only for unrecorded draws, captures differ from mode 0 only by route timing (camera position, race start) and show the vegetation intact. Versions: 0-46 made per 600 swaps (up to 27.7 KB copied), retired to freed 2.8-3.7 submissions and 4-6 ms on multivac, 2-3.5 submissions and 13-14 ms on the Odin, arena never full. Cost per program draw (`gpu_draw_cost_model`, in-run 3/2 A/B every 300 frames): multivac 834-882 ns in mode 2 against 944-997 ns in mode 3 at 126-136 program draws a frame; Odin (v4, untiled skip on) 557-856 against 648-928 ns at 57-188. Mode 3 pays the lookup and the match, so that difference is only the derivation skipped. Complete cost against `gpu_d3d_program` 4 (lists bracketed and timed, no program), two in-run 4/2 A/Bs each: multivac 925 against 962 and 865 against 860 ns a program draw (draw plus list entry), Odin 762 against 670 and 743 against 646 ns, with 5 of 6 Odin windows that ran both modes slower by 5-58 ns. A lookup at every run had cost the Odin 130 against 45 ns of list entry a draw, as about half its runs draw nothing (later tiles); the lookup now happens at a run's first drawn draw, behind a 256-entry direct-mapped cache. Rejected under the stage gate. Routes: local copies of `fh1-race-sustained` and the Odin `native-ab-odin` route with the cvar toggled by `tools/make-ab-route.py`. |
| Research | **Done 2026-10-14.** Four research notes, findings recorded ("engine graphics device class", "D3D command-buffer fixups", "command buffers from assets and run-time recording"; corrections to "D3D command buffers" and "display-list writers"). Recommendation: run DL-0.1 before any design work. | `.local/backlog-research/d3d-renderer-2026-10-14/`; `site/findings/rendering.toml` |
| DL-0.1 | **Passed 2026-10-14.** Census probe (`pinyon_shift_d3d_census`, default off; with it off the probe build matched build X at 2.43 against 2.45 µs of decoder time per decoded draw). Odin race, untiled, 600-frame windows: drawn draws from display lists 64.5-77.5 %, immediate calls 20-30 %, one unattributed buffer 72 a frame; **fallback share 9.5-16 %** (the unattributed buffer, plus list draws whose list changed since its previous run). Desktop tiled race: lists 60-83 %, fallback 5-16 %. List runs byte-identical to their previous run: 83-100 %; every changed list was recorded at run time (the track), so it is re-recorded rather than patched in place, and no list run showed only fixup changes. Origins of list draws: loaded and streamed from assets 46-66 %, cloned 18-64 %, recorded 7-17 %. Writes into watched lists: fixups and stream loads only in the plain census; with the watches re-armed, 5-13 "other" writes into known lists per 600-frame window (about 0.01-0.02 a frame), so a list compiler must still invalidate on any write. Time behind the visible draws: 73-99 % of the decoder (census on), about 7-8 ms of the 9.8 ms census-off decoder plus about 2.7 ms of submission, above the 6 ms bar. | `.local/backlog-research/d3d-renderer-2026-10-14/dl01-probe.md`, `desk-cen.state/logs/runtime.log`; Odin runs `stage1/odin/dl01-{off,cen,rearm,brk}` under `.local/backlog-research/near-native-2026-10-13/` |
| DL-0.2 | **Done 2026-10-14.** From the buffer-switch trace of one race frame: `82468C40` is BeginCommandBuffer (it redirects the device's write pointer into the buffer being recorded) and `823EA3E0` EndCommandBuffer, about 3 a frame; `823EB3D0` opens a tiling bracket and `82469290` closes it, once a frame. Recording runs on its own D3D device, and the indexed draw entry point `82416380` writes into the lists being recorded. | `stage1/odin/dl01-brk/runtime.log`; `site/findings/rendering.toml` |
| DL-0.3 (revisited) | **At the gate 2026-10-15; on by default since the maintainer chose it.** `gpu_d3d_shader_cache` (0 off, 1 verify, 2 on; hot) on the normal PM4 path: a repeated shader load at the same address and size whose memory has not been written since skips the hash, and on Android, which records inline, the shader lookup too; desktop and Linux record on their own thread, so there it only supplies the hash. One write watch is shared with the list compiler. Verify: 0 mismatches over 25.5 M Odin loads (97 % hits) and 93 M desktop loads. Odin, six in-run A/Bs, draw-adjusted: decoder -0.497 ± 0.067 ms (gate -0.5), process CPU -0.52 ± 0.27 ms, submission +0.27 ± 0.17 ms, p99 17.25 to 17.12 ms. Race entered 8/8 and 8/8 on the desktop (7/8 and 5/5 off), 7/7 on the Odin; paused frame bit-identical. | `.local/backlog-research/d3d-renderer-2026-10-14/dl3.md` |
| DL-2.2 | **Not built as designed; closed 2026-10-15.** The slice replays each tiled list whole once per tile. Counters by tiling pass on the desktop race: 13.84 M untiled list draws, 4.32 M in first tiles, 16.32 M in later tiles, and none culled per tile, so replaying per band with the game's per-band culling would replay the same draws. Untiling with one scissor drops 0.40 M of the 16.10 M later-tile draws and was measured CPU-neutral before (see lessons). What the design would need: record each tiled list once with each draw's screen bounds and emit per band only the draws that cross it. Captures with the slice: paused frame bit-identical over 18 toggle pairs; whole route within A/A except a timing variant of the moving-race frame. | `.local/backlog-research/d3d-renderer-2026-10-14/dl3.md` |
| DL-3 | **Failed its gates 2026-10-15.** Whole-frame configuration: every display list compiled, page watch, shader cache, immediate replacement off. Desktop tiled race, four in-run A/Bs: process CPU -0.86 ± 0.63 ms (gate -3), decoder -0.27 ± 0.07 ms, recorder -0.10 ± 0.10 ms, p99 12.75 to 12.58 ms (worse in two of four runs). Steam Deck, seven race runs at 15 W: process CPU -0.91 ± 0.37 ms, decoder -1.03 ± 0.10 ms, recorder +0.11 ms, p99 about 0.45 ms worse; 3 of 4 slice-on launches entered the race against 4 of 4 off. With DL-2.1 on the Odin (+0.01 ± 0.32 ms), the process-CPU gate fails on all three devices. | `.local/backlog-research/d3d-renderer-2026-10-14/dl3.md` |
| DL-2.1 | **Second attempt failed its gate 2026-10-15.** Three additions, each with a hot cvar: a page watch on each compiled list, so a run whose pages are unwritten reads none of the list to validate it (`gpu_d3d_list_watch`); register runs converted once into host order with repeats of the list's own earlier values dropped (`gpu_d3d_list_host_regs`); and a shader cache that keeps each load's hash and translated shader while its microcode pages are unwritten (`gpu_d3d_shader_cache`). Verify: 0 mismatches and 0 watch misses on both devices, 0 shader-cache mismatches over 1-2 M loads a window. Odin, four in-run A/Bs: process CPU +0.01 ± 0.32 ms (gate -3), decoder -0.79 ± 0.10 ms, decoder instructions per draw -33 % (gate -30 %, passes), p99 about neutral, captures within A/A. Each part alone: page watch -0.17 ± 0.09 ms decoder, host register plan +0.04 ± 0.14 (a repeated write was already only a compare), shader cache -0.68 ± 0.06, immediate-call replacement +0.10 ± 0.13 with the render and submission threads +0.13 ms each (net negative). None shows in process CPU, whose noise is ±0.4-0.8 ms a pair. What is left of the decoder's 7.9 ms a frame: backend draw path 22 %, register writes 14 %, list replay loop 10 % (2.04 G cycles against 3.21 G), kernel 8 %, copies 6 %; removing every non-backend cost would give at most about 2.8 ms of decoder. With a watch on, the desktop race route failed to start the event in 5 of 15 runs (8 of 8 without; the same frame as an earlier no-watch failure, so the route's boot-timing flake made more frequent); Odin 12 of 13. | `.local/backlog-research/d3d-renderer-2026-10-14/dl21b.md`; `stage1/dl21b-reg.txt`, `queue41.sh`, `queue42.sh` under `.local/backlog-research/near-native-2026-10-13/` |
| DL-2.1 | **First attempt failed its gate 2026-10-14.** Slice: every display list, compiled, plus the two immediate draw calls `82416380` and `82415F68` replaced outside recording (tiled draws included: the markers replay per tile with their predication). An immediate call is declined, with a counted reason, when it is recorded, a query, binds a shader or has per-tile, clip or wait state pending; otherwise its description goes to an arena by guest frame, a 16-byte marker goes into the stream and the five dirty masks are cleared. Lists are keyed by address and length, compiled at their second run, checked on raw header and control words at each run, with values, draw words and microcode read live so fixups act as bindings; a failed check decodes normally and recompiles, with backoff and eviction. Cvars `pinyon_shift_d3d_slice` (0, 1 verify, 2 on; hot) and `gpu_d3d_list_compile` (-1 follows the slice). Verify: 0 mismatches over about 1 M desktop and 1.77 M Odin list draws, 0 uncovered packets for immediate calls; paused frame bit-identical, whole-route captures within A/A. Odin, four in-run A/B runs pooled, draw-adjusted: process CPU +0.07 ± 0.31 ms (gate -3), decoder -0.32 ± 0.11 ms, submission -0.02, guest render thread +0.12 ± 0.04 ms; decoder instructions per draw about -20 % (gate -30 %); p99 slightly worse in three of four runs (17.09 to 17.18, 17.14 to 17.26, 17.06 to 17.39, 17.15 to 17.12 ms). Flat profiles: packet dispatch fell from 3.07 to 0.80 G cycles but checking every list word added 3.21 G; the backend draws, register writes, shader hashing and texture binding are unchanged; the decoder is stall-bound, so a fifth fewer instructions barely moves its cycles; building a description costs the guest more than writing its own packets. | `.local/backlog-research/d3d-renderer-2026-10-14/dl21.md`; Odin runs `stage1/odin/dl21-*`, `stage1/dl21-reg.txt` under `.local/backlog-research/near-native-2026-10-13/` |
| DL-1.2 | **Passed on the desktop 2026-10-14.** The HUD is drawn through a D3D-level path: a hook at the indexed draw call `82416380` writes a tagged PM4 NOP marker before the call's own packets, hooks in the shader bind record its constant and shader loads, and at the call's exit a draw description is built from the device's shadow registers and dirty masks (registers in flush order, shader loads, base vertex, draw words) and handed to the decoder through a ring. In draw mode the decoder skips the packets the description covers and issues the draw from the description at the guest draw's place in the stream; waits, events, coherency writes and fences still run. Cvars `pinyon_shift_d3d_draw` (0 off, 1 verify, 2 draw; hot) and `pinyon_shift_d3d_draw_scope` (0 the HUD target, 1 every untiled, unpredicated indexed call, recorded lists left to PM4). Verify: 4.68 M HUD draws, about 600 M registers, 0 mismatches; scope 1: 3.05 M draws, 5,075 mismatches, all one `VGT_INDX_OFFSET` a frame patched into a recorded list after recording. Captures: the path toggled on a paused frame, 0 differing pixels in four runs; whole-route captures inside the A/A spread. Desktop in-run A/B, race: mean +0.01 ± 0.02 ms, p95 +0.02 ± 0.05, p99 -0.36 ± 0.19. Three of 21 route runs never entered the race, all with the path on in some mode (car off the line before the event); reruns passed, so a pacing effect on a wall-time input is not ruled out. No cost saving yet: the game still writes the PM4 and the decoder walks it. Found that `8240F4D8` is Resolve, not a HUD draw wrapper. | `.local/backlog-research/d3d-renderer-2026-10-14/dl12.md`; `site/findings/rendering.toml` |
| DL-1.1 | **At the gate 2026-10-14, not a clear pass.** `gpu_d3d_census_skip_visible` (hot, default 0) makes the PM4 path do no work for draws in buffers DL-0.1 counts as visible: mode 1 skips draw packets (state derivation, recording, submission; shader loads deferred to the next executed draw), mode 2 also shader constants, mode 3 also every other register write except the ranges fences, render targets, windows, copies and resolves read. Events, waits, memory writes, interrupts, swaps, queries, nested buffers and EDRAM copies always run (about 34 resolves a frame inside visible buffers still ran); the race finished in the same game state with only the HUD drawn. A lean census mode (`pinyon_shift_d3d_census_lean`, classification only) keeps the race at 60 fps; both sides pay its 2.6 ms of decoder. Odin race, in-run A/B every 180 frames, both orders, regressed on decoded draws: mode 3 (4 runs) process CPU -6.28 ± 0.42 ms against a gate of 6.17 ms (1,441 visible draws × 2.2 µs + 3 ms), per run -6.08, -5.97, -5.96, -7.57 against 6.37, 6.37, 6.25, 5.69; decoder -3.46 ms (11.20 to 7.96, -31 %, short of the 50 % no-go line in note 04), submission -1.57 ms, render thread -0.60 ms. Mode 2: -5.62 ± 0.47 against 6.25; mode 1 (1 run): -4.22 ± 0.89. Net of the native draw cost the ceiling is 3.1 ± 0.4 ms a frame, against the 3 ms bar. The skip still walks every packet of the visible buffers (understates the ceiling by perhaps 1-2 ms) but also drops texture and vertex uploads and write-watch work a native renderer would keep (overstates it by about as much). | `.local/backlog-research/d3d-renderer-2026-10-14/dl11.md`; Odin runs `stage1/odin/dl11-*`, `dl11b-*`, tables `stage1/dl11-mode{2,3}.txt` under `.local/backlog-research/near-native-2026-10-13/` |
| DL-0.3 | **Rejected 2026-10-14.** `gpu_shader_load_memo` keyed the shader by (type, guest address, dword count), each entry held by a one-shot write watch on its microcode. Verify: 0 mismatches in 30.1 M and 27.0 M loads; hit rate 96.2 % (1,024 entries) and 99.77 % (4,096, two-way). Four in-run A/Bs on the Odin race: raw decoder differences were within noise because the memo-on windows decoded 170-590 more draws in every run (the toggles fall on the same route frames, so window means carry the scene phase); adjusted for draws, decoder -0.32 ± 0.09 ms pooled, process -0.05 ± 0.22 ms, frame unchanged, against the -0.5 ms gate. The 0.9 ms estimate was an inclusive profile share. Code reverted; patch kept. | `.local/backlog-research/d3d-renderer-2026-10-14/dl03.md`, `dl03-sdk.patch`; `site/pages/lessons.md` |

## Sources

- [NEAR_NATIVE_RESEARCH.md](NEAR_NATIVE_RESEARCH.md): Where the overhead
  is, NN-0.10 (G0), NN-2.2, NN-2.6, NN-2.7.
- [NATIVE_PORT_BACKLOG.md](NATIVE_PORT_BACKLOG.md) NP-9.5;
  [PERFORMANCE_BACKLOG.md](PERFORMANCE_BACKLOG.md) "What the fast ones do";
  [DESKTOP_RENDERER_BACKLOG.md](DESKTOP_RENDERER_BACKLOG.md);
  [RECORDER_REPLAY_BACKLOG.md](RECORDER_REPLAY_BACKLOG.md).
- `docs/native-renderer/` (RESEARCH.md, XENOS_RETIREMENT_BACKLOG.md,
  GUEST_VISIBLE_RENDER_DEPENDENCIES.md, archive/RENDER_PASS_CENSUS.md).
- Prior-art links are in the 03 note.
