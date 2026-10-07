# FH1 renderer test automation

This is a Forza Horizon 1-only unattended test path. It launches the real game
and the FH1 native renderer, the only renderer, with a synthetic controller, writes full-resolution PPM
captures, and exits through the normal window-close path. Scripts use completed
guest-output frames by default; `# clock-hz N` makes their frame numbers an
explicit wall-time clock for stock-versus-unlocked comparisons. It does not use
computer use, screen scraping, or a physical controller.

Vulkan is the sole supported graphics API. Direct3D 12 is legacy and
unsupported; its retained diagnostics and historical comparisons do not gate
new releases or DLC support. Vulkan translates shaders during play and uses
shader storage; normal setup prepares that storage before the first launch.

Follow [AGENTS.md](../../AGENTS.md) for save handling. Scripted routes use
`tools/run-fh1-render-test.py`, which copies a pinned seed into a private run
directory. Pin a read-only snapshot of the AppData save once with the game
closed; the runner never writes the source save or seed:

```powershell
python tools/create-render-seed.py appdata-2026-09-27 `
  --state-root "$env:LOCALAPPDATA\PinyonShift\source\0.1.0\.local\preview" `
  --note "Free roam next to the Gauntlet sign-up"
python tools/run-fh1-render-test.py config/render-tests/fh1-race-sync.fh1test `
  --state-root .local/render-seeds/appdata-2026-09-27 --configuration RelWithDebInfo --hidden `
  --game-argument=--gpu_backend=vulkan --seed-vulkan-shader-storage
```

The seed holds `user`, `config`, the FH1 shader catalogs and a `seed.json`
manifest with profile hashes; `create-render-seed.py` refuses to overwrite
one. The new-player opening (`fh1-opening-sync`, the matrix's second race
event) needs a seed without a profile: copy an existing seed's `config`,
`cache` and `seed.json` into a new directory with an empty `user` (for
example `.local/render-seeds/fresh-2026-09-28`) and pass `--fresh-profile`,
which lets the runner accept a state root with no `ForzaProfile`.
`fh1-buy-car` buys a car in the private copy of the profile and waits for
the game to save its card thumbnail (`Thumbnail_7.xdc` under the run's
`ForzaProfile/Thumbnails`); decode it to check that resolves reach guest
memory. Output-paced routes are sensitive to frame rate because menus advance in
wall time: the committed routes were recorded with `--hidden` (about 100
frames/s here), and a visible window at 120 Hz ran about 143 frames/s and
missed the menu inputs. Use `--hidden` until routes wait on game state. Each
runner invocation copies only `user` and `config` from its seed into a private
sibling directory beside its output. FH1 may autosave in the private copy, but
the selected seed is never written. Cache contents
are deliberately not shared between runs. `--seed-shader-storage`
`--seed-pipeline-prewarm` copies the immutable FH1 native shader/pipeline catalog
and its allowlist; it no longer seeds writable `.xsh`/`.xpso` stores.
Supplying `--shader-pack` automatically seeds the catalog because the shipping
backend needs both pieces.

Pass `--baseline-dir <previous-output>` to compare each capture named by an
`# expect-image` line with a known-good run. Those lines set limits for mean
absolute error, root-mean-square error, and changed-pixel ratio. Dynamic race
and free-roam shots intentionally allow traffic, camera, and simulation drift;
the static SELECT map has a tight limit. Baselines contain game imagery and
therefore remain local rather than being committed. Creating such a reference
requires the explicit `--record-baseline` switch; a scenario with image
expectations otherwise fails before launch, preventing a missed reference from
being reported as a successful visual gate.

`# expect-performance` sets maximum median frame time, minimum presentation
rate, and the permitted main-loop-rate range. The legacy telemetry field is
named `simulation_tick_count`, but the measured hook is the FH1 application
loop and must not be interpreted as an individual physics-step counter.
`# require-native` belonged to the removed race pilot (`0e88456`); a script
line with it is now an ordinary comment. A run fails for missing or wrong-frame
captures, blank output, renderer/GPU/device-loss errors, a missed capture frame,
or an abnormal process exit. The PowerShell launcher owns the exact child PID
and terminates it if the render-test timeout expires.

`wait <frame> <max-frames> <condition> [argument]` makes an output-paced
route wait on game state instead of timing: at `<frame>` the script clock
holds (inputs keep their state) until the condition holds, and later steps
keep their spacing from that point. Conditions are `vehicle` (a vehicle pose
update arrives), `vehicle-moved <units>` (the car has moved that far since
the wait began, e.g. once a race countdown ends), `movie <text>` (the
guest opens a movie whose lower-case path contains the text) and
`file <text>` (the guest opens any file whose lower-case path contains the
text, for screens that load their own assets; opens in the 60 output frames
before the wait count, since a screen often loads right after the input that
opened it). To find the files a screen
opens, run a route with `--game-argument=--fh1_render_test_log_file_opens=true`:
every open is recorded as `fh1.render_test.file_open` with its output frame. Each wait
records `fh1.render_test.wait` with the frames waited; exceeding
`<max-frames>` fails the run with `wait_timeout`. `fh1-race-start-wait`
uses it to capture the race only after the car moves.

`hostkey <frame> <key>` presses and releases a key on the game window at
`<frame>`, through the same window listeners as a real key press, so a route
can drive host-drawn screens that the scripted controller cannot reach (the
F6 settings screen, the F8 photo). Keys are `f6`, `f8`, `enter`, `escape`,
`up`, `down`, `left`, `right` and `space`; each press records
`fh1.render_test.hostkey`.
`cvar <frame> <name> <value>` sets a flag at `<frame>` on the UI thread, as a
settings change does, and records `fh1.render_test.cvar`; `fh1-scale-switch`
uses it to switch the resolution scale at run time.
`snapshot <frame> <name>` writes the guest's 512 MB of physical memory (the
title's physical allocations, not the virtual heaps) to `<output>/<name>.mem`,
and `poke <frame> <hex physical address> <float>` stores a big-endian float
there, both from the frame-clock thread while the title runs (a snapshot may
tear). `tools/scan-guest-snapshots.py s0.mem s1.mem s2.mem --min 0 --max 1
--increasing` lists the words that step by the same amount between snapshots
taken at equal spacing, such as game clocks. Heap layouts differ between
runs, so confirm a candidate with `poke` in a run that found it; delete the
snapshots afterwards (1.5 GB for three). For that, `mark <frame>` keeps a
copy of the title's committed virtual heap pages (0x00010000-0x7EFFFFFF,
about 110 MB in free roam) in memory, and `scanpoke <frame> <min> <max>
<float> [<min step> <max step> [<first> <count>]]` pokes every float in
`[min, max]` that rose by the same step (within 2 %) between each pair of
three or more marks, or only candidates `first` to `first + count - 1`, then
records `fh1.render_test.scanpoke` with the count and the first 64 candidates
as `index:address:value:step` (`*` where poked). Poking hundreds of values
can crash the title: list them first with a count of 0, then narrow the
range and step. The time of day was found this way, in seconds
(`scanpoke <frame> 40000 50000 79200 200 350` turns free roam to night).
`hostclick <frame> <left|right> <x> <y>` moves the pointer and clicks at
`(x, y)` in the title's 1280x720 layout space, mapped onto the painted guest
output, which is the space the host UI lays its rows out in. The host UI
records `hostui.open`, `hostui.screen`, `hostui.closed` (drawer, input
listener and guest input capture released) and, once per screen and output
size, `hostui.layout` with its drawn extent against the 90 % safe area;
`tools/check-fh1-settings-gate.py` checks the `fh1-settings-gate` route with
them. `xamdialog <frame> message|keyboard` opens a sample XAM message box or
keyboard through the host dialogs and records how it closed
(`fh1.render_test.xam_dialog`); `fh1-xam-dialogs` drives both with keys.

There is no renderer to choose: `fh1_renderer` was removed with the Xenos
and `native-shadow` renderers (`a5b28e1`, `bccf126`). Every
`fh1.render_test.capture` event still records `presenter` and
`session_renderer`; both are always `native`.

Use the resolution scale the pack was produced for. Symmetric 1x, 2x and 3x
(`--draw_resolution_scale_x/y`) are supported; any other scale fails
graphics setup with an error, and there is no fallback renderer. A draw
whose shader is missing from the pack is dropped and the miss is recorded
under the run's `cache/fh1-shader-misses` (see
[pack misses](SHADER_PACK_FORMAT.md#pack-misses-and-self-repair)); check the
run's log for pack misses before trusting its captures.

`# expect-distinct-presentation <minimum-hz>` rejects repeated host presents;
only distinct completed FH1 frames count. Use repeatable
`--game-argument=<cvar>` options for cadence and resolution qualification. The
launcher serializes the list so multiple PowerShell options cannot be mistaken
for launcher parameters.

`# expect-capture-mae <first> <second> <minimum>` proves that a scripted mode
transition actually happened before a baseline can pass. The map scenarios use
it to reject tutorial profiles where SELECT is intentionally unavailable.

`--collect-pass-inventory` recorded ranked FH1 pass-family identities and GPU
nanoseconds from the Xenos draw observers. The native renderer does not feed
that inventory, so on the current build it is empty.

The committed scenarios cover:

- `fh1-race-sync.fh1test`, `fh1-modes-sync.fh1test`: synchronized on game
  state, so repeated runs reach the same content: car select with its
  thumbnails and a race start (the Gauntlet), and free roam, pause, map and
  photo mode from seed `appdata-2026-09-27`;
- `fh1-opening-sync.fh1test`, `fh1-rewind-sync.fh1test`: the new-player
  opening and a rewind from a profile-free seed (`--fresh-profile`);
- `fh1-buy-car.fh1test`: buys a car in the autoshow and waits for its saved
  thumbnail;
- `fh1-rally-car-database.fh1test`: checks the normal owned Rally database merge
  and native entitlement cache against the imported licence and package's
  reference database, including tyre, suspension and engine option counts.
  Requires a prepared owned seed with an existing Rally ledger and preserves
  it byte for byte. This does not qualify purchase, driving or the upgrade UI;
- `fh1-rally-service-entry-guard.fh1test`: attempts Rally selection from Dak's
  Garage, leaves the service, then resumes championship 7 stage 2 with the
  retained Escort. Requires the restored seven-car seed described in the
  [DLC backlog](../DLC_BACKLOG.md). `# expect-rally-service-entry-guard` checks
  native control ownership, disabled selection across the attempted Enter,
  restored free-roam availability and subsequent player selection. The existing
  resume and HUD gates also require a live race and an unchanged earned ledger.
  It does not qualify other services, sustained handling or stage completion;
- `fh1-rally-full-garage-stage-finish.fh1test`: enters the saved championship-7
  checkpoint through F6 with the complete owned-car profile. Pass
  `--game-argument=--fh1_render_test_rally_ai_driver=true` to use the native AI
  controller for finish/persistence diagnostics. The default-off flag is ignored
  outside render tests; `# expect-rally-test-ai-driver` requires its native
  controller event and reports player steering as unqualified. Native finish
  and earned-progress gates are separate from visual review of both results
  captures. It does not capture the loading transition: that frame may be
  intentionally black. Recipe 7 grounds Rally finish targets through the native
  terrain query; the stage-two and stage-three backgrounds pass visual review, while other
  finish views remain unqualified;
- `fh1-rally-full-garage-stage-reload.fh1test`: uses the preceding run's private
  state as its source, reloads and resumes stage three through F6, then drives
  with scripted throttle. Run without the diagnostic AI flag. Preserve the
  original source state and compare native saves and the earned ledger as
  described in the [DLC backlog](../DLC_BACKLOG.md);
- `fh1-rally-full-garage-final-stage.fh1test`: resumes an earned 7/4 checkpoint
  with the same complete owned-car profile and diagnostic native AI flag,
  waits for the native result, then exercises results navigation and return
  to playable free roam. This uses output frames because native readiness
  waits cannot be combined with a wall-time clock. It is a gameplay diagnostic,
  not a performance or player-steering qualification. Completion and the
  preceding three saved times require a separate native-save audit; this route
  is still being qualified;
- `fh1-rally-full-garage-series-reload.fh1test`: starts from an actually earned
  completed championship-7 save with the full seven-car garage and stock Escort
  selected at Dak's Garage. Uses ordinary owned-content preparation, reloads
  its four stage times and single completion, drives through the garage area
  with scripted reverse, handbrake, throttle and steering, then opens/closes the
  map. Run without diagnostic AI. The source save, native database, purchased
  parts and ledger require the separate preservation audit described in the
  [DLC backlog](../DLC_BACKLOG.md). This qualifies initial free-roam control
  and completed-record reload; full-stage player handling remains open;
- `fh1-long-drive.fh1test`: a long scripted race drive for stability;
- `fh1-smoke.fh1test`: launch, capture, and clean self-termination;
- `fh1-fmv.fh1test`: startup/FMV composition with
  `--include-opening-movies`;
- `fh1-free-roam.fh1test`: driving view, HUD, and minimap;
- `fh1-map.fh1test`: SELECT map roads/icons and return to free roam; and
- `fh1-pause.fh1test`: pause overlay and return to free roam; and
- `fh1-photo-mode.fh1test`: enter and leave FH1 photo mode; and
- `fh1-source-60.fh1test`: sustained driving with a real distinct-frame gate;
  and
- `fh1-scale-switch.fh1test`: free roam switched from 1x to 2x and back at
  run time (stage both packs with two `--shader-pack` arguments); and
- `fh1-hfr-modes-control.fh1test` / `fh1-hfr-modes-unlocked.fh1test`: paired
  wall-time free-roam, SELECT-map, pause, and resume qualification; and
- `fh1-race.fh1test`: event entry, car/start menus, live race HUD, and motion
  without completing the event.

This is not a synthetic renderer unit test and does not bypass the real FH1
runtime. A normal host window may exist while the run is unattended; hiding or
reimplementing it adds no test reliability. Map and race traces still require a
known progressed local seed at their expected location. The runner copies that
seed before launch; unknown or locked scene state fails before it can become a
visual baseline.

## Diagnostics

These settings are passed with `--game-argument=` (or `-GameArguments` for
`launch-preview.ps1`). All are off by default and stay out of timing runs,
except the resolve read-back, which is on by default.

| Setting | Effect |
| --- | --- |
| `--fh1_native_dump_frames=N,M --fh1_native_dump_dir=<dir>` | Writes the presented front buffer of the listed swaps as PPM |
| `--fh1_resolve_dump_dir=<dir>` | Writes every resolve's output bytes (the scaled range when scaling) to numbered files, waiting for the GPU after each |
| `--fh1_frame_census=true --fh1_frame_census_path=<file.jsonl>` | Metadata-only census of surfaces, resolves, textures and primitives per 60-frame window; see the [frame contract](NATIVE_FRAME_CONTRACT.md) |
| `--fh1_native_gpu_profile=true` | GPU time per phase in the periodic stats: executor transfers, resolves and clears, plus texture cache loads split into `texture_reloads` (data a resolve invalidated) and `texture_loads` (everything else); also the executor's CPU time per phase (target preparation and binding, transfers, resolves). On Vulkan: transfers, resolves, clears and `frame` (GPU time from the frame's first timed phase to its swap, idle gaps included) |
| `--vulkan_diagnostic_checkpoints=true` | Vulkan on NVIDIA: marks the command stream (draw start and end, copies, texture loads and their dispatches, executor resolves, transfers and clears) and, if the device is lost, logs the last markers the GPU began and finished and the shaders of the draws around the last one begun |
| `--vulkan_async_submission=false` | Vulkan: replays and submits command buffers on the GPU commands thread instead of the `GPU Submission` worker; `--vulkan_async_submission_split_draws=<n>` sets how many draws a submission holds before the worker gets it (default 1024, 0 splits only at swaps) |
| `--fh1_native_readback_new_resolves=false` | Stops copying one-off resolves (such as saved car thumbnails) back to guest memory |
| `--fh1_debug_log_draws=true` | Logs every draw (copies included) with its index in the frame, EDRAM mode, primitive, shaders, render target, blend, copy registers and the pixel shader's texture fetch constants; use it on a frame replay |
| `--fh1_debug_skip_draws=<first>-<last>[,<first>-<last>...]` | Skips those draw indices in every frame: bisect a replayed frame for the draw that causes a fault, keeping a known contributor skipped with a second range |
| `--fh1_debug_null_fetch=<draw>:<slot>` | That draw binds a null texture for that fetch constant (logged as "completely invalid"), to tell texture faults from shader math |
| `--perf_critical_path_trace=true` | Correlated title/PM4/submission/present trace |

The executor logs its skip counters, memory (`FH1 native executor memory
MB`) and transfer statistics every 600 swaps. With
`readback_resolve = none`, large resolves to ranges no resolve wrote in the
last few frames are copied back to guest memory before the next command the
guest CPU can observe; this is how the game's saved car thumbnails get real
images. Resolves repeated every frame are not read back.

## Frame dumps and offline replay

A frame dump records one frame's command packets, starting registers, bin
state, shaders and every guest range it reads. Record one from a normal or
render-test run at 1x:

```text
--fh1_frame_dump_frame=<frame> --fh1_frame_dump_path=<file.fh1frame>
```

`tools/replay-fh1-frame.py <dump> --state-root <seed>` replays it with the
title suspended and compares the front buffer; `--write-golden` stores the
result as the golden replay beside the dump (`<dump>.native.golden.bin`). `tools/test-fh1-frame-replays.py
<directory> --state-root <seed>` replays every dump in a directory against
its golden replay: this is the offline regression suite for the executor.
Replays are deterministic. Dumps hold guest memory and stay under `.local`;
like the render tests, replays copy the seed to a private state directory.
Dumps are recorded on either backend and replay on either backend: with
`--build-directory out/build/win-amd64-vulkan --game-argument=--gpu_backend=vulkan`
the recording run or the replay runs on Vulkan, and a `.replay.bin` compares
with the other backend's (the front buffer is tiled, little-endian
2_10_10_10 with red in the high bits; the two backends differ only in sparse
edge samples on the four goldens, and by at most 8 of 1023 per channel on a
Vulkan-recorded free-roam frame replayed on D3D12). A Vulkan dump replays on
Vulkan with no differing words; D3D12 dumps of 3D scenes differ from their
own recorded front buffer in about 2 % of words (edge samples).
