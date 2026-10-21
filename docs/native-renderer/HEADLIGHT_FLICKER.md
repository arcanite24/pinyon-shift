# Oncoming headlight flicker (#531)

Status: investigating. The shadows-off fix for #532 restores the projected
headlight pool on the road at night. It does not establish that the separate
oncoming-light flicker in [#531](https://github.com/arcanite24/pinyon-shift/issues/531)
is fixed. The original report also reproduces with HDR off.

## Reproduction route

`config/render-tests/fh1-night-traffic.fh1test` uses the Gauntlet free-roam
start from the pinned `i532-sh-off` seed on multivac. For another machine,
make a read-only seed of a profile at that location using
`tools/create-render-seed.py`. Never use the player's writable state for this
test. The [render-test workflow](FH1_RENDER_TEST_AUTOMATION.md)
describes the private state copies.

The route fixes time at 23:00 and enables bloom. The example requests shadows
off; repeat with `--pinyon_shift_fh1_shadows=true` to compare the setting. At
night the shadow passes still run, as required for projected headlights.
It applies light throttle from 20 to 30 seconds, then coasts until after
140 seconds. It can hit a guardrail or leave the road; it does not steer
around traffic. The 60 Hz logical clock gives the same two-minute observation
window at each output-rate setting. It must not contain output-clock `wait`
steps. Discard a run if `night-start` is not in free roam or no oncoming
traffic appears.

For Windows, repeat with output limits of 30, 60 and 120, using a new output
directory each time:

```powershell
python tools/run-fh1-render-test.py config/render-tests/fh1-night-traffic.fh1test `
  --state-root .local/render-seeds/i532-sh-off `
  --build-directory out/build/win-amd64-release `
  --output .local/headlights-60 --timeout 300 `
  --game-argument=--pinyon_shift_cheats=true `
  --game-argument=--present_hdr=false `
  --game-argument=--pinyon_shift_fh1_shadows=false `
  --game-argument=--pinyon_shift_fh1_render_fps_limit=60
```

Record video throughout the run. The seven sparse captures confirm location
and lighting; they cannot decide flicker. An output limit is not a measured
frame rate. Keep the performance CSV and recording timestamps, and inspect
consecutive frames around every oncoming encounter. Repeat with shadows on.
An exit code of zero only means the script completed.

On Android, copy the seed into a new `files/qualification/<run>` directory,
including `title-update-v4` for a v4 build. Pass that directory using
`env.PINYON_SHIFT_STATE_ROOT`, and pass the route and a new capture directory
using `env.PINYON_SHIFT_FH1_RENDER_TEST_SCRIPT` and
`env.PINYON_SHIFT_FH1_RENDER_TEST_OUTPUT`. Do not use
`pinyon_android.py run --seed`, which replaces the player's state. A
`screenrecord --time-limit 160 --bit-rate 12000000 <private-run>/night.mp4`
preserves the encounter between captures. Screen recordings may have variable
cadence and repeated frames; use their timestamps instead of assuming the
nominal recording frame rate. Restore device settings after testing.

## Evidence and remaining gate

The October 18, 2026 exploratory Odin 2 Portal run used the installed 0.5.1
v4 APK: host `bd5966272392`, SDK `71e09d406a96`, Adreno 740 with the
automatically selected `turnip-gen8-v37` driver, 1x, HDR off, bloom on and
shadows requested off. This is an older baseline than the
`45d1739` / `b528422` development snapshot; it is not validation of a new
renderer fix. Local recordings and logs are under the B11 worktree's
`.local/android/` directory and are not repository assets.

Three recordings cover the 20-to-140-second route window. In the performance
CSV's 25-to-140-second interval, the sum of `source_frame_count` divided by
the summed `frame_time_us` gives:

| Requested output limit | Measured source frames/s |
| --- | ---: |
| 30 | 30.00 |
| 60 | 59.93 |
| 120 | 66.84 |

The last run is not a 120 fps qualification. All three windows report zero
duplicate presentations and zero memory-export draws; the summed simulation
time advances at wall-clock rate with zero invalid deltas. These are exploratory
runs with recording overhead and cold caches, not performance benchmarks.

The reviewed 60-limit recording contains an oncoming convertible at roughly
101 seconds. Its two headlights remain visible in the inspected consecutive
recording frames. This encounter did not reproduce the reported flicker.
The executor's cumulative `draw_in_occlusion_query` count stays at one
through the night-driving window, rather than increasing with the car's
approach. No new blocking legacy host query brackets those sampled frames.
This does not rule out shader-based depth visibility, resolve ownership or
other cars and distances.

An exploratory Windows 0.6.0 baseline on the RTX 4080 reached all seven night
captures at each requested limit. Sampled frames from the first 143.5-second
window GDI recording were black despite valid guest captures, so that method's
recordings are excluded. The first 120-limit run also failed the runner's
GPU-log gate on an indirect-packet overflow near 108 seconds, despite reaching
the scripted stop. No connection between that packet error and the headlights
was established.

A second Windows pass recorded the game's owned window with FFmpeg Windows
Graphics Capture (`gfxcapture=hwnd=<handle>:max_framerate=120`), scaled to
1280x720 and encoded with NVENC. Capture and teardown stayed inside the game
reservation. All three videos contain gameplay for about 141.9 seconds; all
three routes passed the GPU-log gate and reached their seven captures. The
settings were 1x, HDR off, bloom on and shadows requested off. With the same
25-to-140-second performance-CSV calculation:

| Requested output limit | Measured source frames/s |
| --- | ---: |
| 30 | 29.97 |
| 60 | 59.79 |
| 120 | 91.34 |

The inspected consecutive recording frames at video times 82–83 seconds
(30 limit), 53.5–54.5 seconds (60 limit) and 101–101.6 seconds (120 limit)
keep both oncoming headlights visible. These selected windows do not qualify
the entire drive. The legacy query-draw counter stays at one in all three
runs, and the measured interval has zero duplicate presentations and invalid
simulation deltas. The 120-limit run is not a 120 fps qualification. Recording
overhead and other fleet work make these unsuitable as performance benchmarks.

These Windows runs used a copied local executable with SHA256
`FC46C811D0970C419FD34EF9151216BDD50CDC6E3584E66AF001F4F85A551704`;
its exact source revision is not established by the available build manifest.
They do not validate a newly built development snapshot. Artifacts are under
`.local/desktop-wgc-{30,60,120}` and the matching `.mp4` and `.state` paths.
Capture contents and the GPU log both need checking before treating a
completed route as visual evidence.

The issue remains open until a failing encounter is captured, its light draw
and depth/resolve inputs are identified, and a correction survives a
two-minute oncoming-traffic drive on current desktop and Android builds.
The sparse scene captures and the shadows-off headlight-pool check do not
meet that gate.
