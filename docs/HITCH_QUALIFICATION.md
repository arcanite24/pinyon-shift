# Qualifying first-visit and recurring hitches

Use `fh1-hitch-drive.fh1test` for a free-roam drive and
`fh1-hitch-race.fh1test` for the sustained Gauntlet route. Both keep only a
final capture: GPU readback stalls from intermediate captures must not be
counted as gameplay hitches. The race route checks that the vehicle exists,
the race loads and the vehicle moves; it does not complete the race.

Run through `tools/run-fh1-render-test.py` with a pinned seed. It copies the
seed to a private state directory; never run a timing experiment against a
writable player save. Keep the executable, seed, settings and GPU driver
identical within each comparison. On a shared machine reserve the game and
exclude heavy builds while collecting timings.

Validate the measured scene as well as the seed. Identical input scripts can
reach different positions when loading or traffic changes. Compare captures
and vehicle poses before treating a frame-time difference as a regression.
For a stationary comparison, hold the handbrake: the brake pedal selects
reverse once the car has stopped. Warm that stationary scene itself, rather
than assuming a preceding drive compiled its pipelines. Reject a repeat if
traffic moves the car. Check the race HUD's elapsed time when qualifying a
60-second race; startup and route-clock time do not establish racing time.

Useful diagnostic arguments (each supplied as `--game-argument=...`):

```text
--pinyon_shift_hitch_sample_ms=35
--pinyon_shift_hitch_sample_threads=GPU Recorder,GPU Commands,GPU Submission
--pinyon_shift_sql_profile=true
--vulkan_log_pipeline_waits_ms=1
--gpu_log_long_wait_reg_mem_ms=25
--fh1_native_gpu_profile=true
```

Keep an uninstrumented repeat as well: stack sampling suspends the sampled
threads, and per-phase GPU queries add work. The runtime log names pipeline
replay waits and the sampled guest/host stacks; the session performance CSV
records frame times, title GPU-fence waits, texture activity, GPU timing
samples and GPU timing drops. The pipeline hit/miss CSV columns are not
populated by the Vulkan backend: zeros there do not prove a warm cache.
Use the stored-pipeline load count, pending-bind draw log and replay-wait
log to establish pipeline activity. Do not treat a missing GPU timing
sample as a zero-duration GPU frame.

## Cache policy

The runner leaves Vulkan shader/pipeline storage out by default. That
measures a first visit **without application storage**, with the driver's
existing cache still present. It does not measure a cold GPU driver.
Never erase a player's driver cache to make a test cold.

For the warm repeat, make a private copy of the original pinned seed and
stage the completed run's `cache/shaders` into that copy. Pass this warm
seed with `--seed-vulkan-shader-storage`. Its user and configuration must
still match the original seed: a completed run can save a new position or
progress. The runner copies its `.xsh`, `.vk.xpso` and device-specific
Vulkan pipeline cache into another private state. Copying only the original
seed would not warm pipelines first encountered on the measured route.
Shader preparation alone cannot
know every combination of shader, render pass, blend and depth state that
future gameplay will request. Prepared artifacts remain local to the
owner's installation; do not distribute game-derived shader/catalog data.

## Day, night and location comparisons

On the drive route, hold noon or midnight with
`--pinyon_shift_cheats=true` and `--cheat_time_of_day=12` or `0`.
Check the final image: an event script can hold its own time, which the
trainer deliberately respects. A free-roam lighting comparison does not
qualify an eight-car night race.

For #683 compare 1x and 3x, with a 120 fps cap, HDR, single-sample rendering
and `pinyon_shift_fh1_env_map_rate=1`. Preserve these settings in the warm
repeat. Full-rate reflections are a test input, not an established cause.
For #633 the supplied sunset head-to-head screenshot has no event name or
world coordinates; the Gauntlet fixture alone cannot qualify that location.

Keep loading, steady driving and the final capture separate. Report p95,
p99, worst frame and counts above 25, 50 and 100 ms for the same retained
window, plus total title GPU-fence wait, pending pipeline draws and replay
waits. Keep slow
frames in the window; filtering them by frame time hides the behavior being
investigated. A first-visit improvement does not establish a fix for a
periodic warmed race hitch.
