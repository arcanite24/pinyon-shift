# Backlog

## Epic: Soak-test diagnostics and performance

Use the 2026-08-25 long-play installation evidence to turn the current
performance and graphical-correctness signals into reproducible fixes.

- [x] Gate high-volume `M3_TRACE`, `M4_TRACE`, and `M5_TRACE` reentry diagnostics in release gameplay behind `PINYON_SHIFT_REENTRY_TRACE=1`, with a single opt-in activation marker for verification.
- [x] Capture session-specific per-frame performance CSVs in Release builds, including frame time, FPS, draw calls, command-buffer stalls, and texture/pipeline cache hit rates.
- [x] Add defensive geometry-list repairs that normalize invalid relocated-entry counts while preserving the existing range and readability crash guards.
- [x] Suppress per-frame VIZ-query INFO logging; the controlled capture reduced runtime logging from about 60 to 4.6 lines per second without materially changing sustained heavy-scene frame times.
- [ ] Reproduce and fix the startup fail-fast at unregistered indirect target `0x820239A8` (`lr=0x82DE7360`, crash ID `pscrash-v1-abc5dbd98776afc369e4`), including a regression test for the missing target or discovery path.
- [ ] Investigate the captured geometry-index corruption signatures, including counts as high as `0xFF` and unreadable secondary-list pointers; correlate the repair bursts with the startup crash and visible glitches, then remove the underlying ownership or relocation defect.
- [ ] Instrument and optimize the texture-cache miss/upload path. Separate lookup, decode, upload, fence wait, and eviction time, and cover cold-start spikes such as the 1.18-second frame with 266 texture misses.
- [ ] Explain why the renderer queue remains at its maximum depth of eight during gameplay by adding bounded CPU submission, GPU completion, fence-wait, and present timing; use that evidence to identify the actual backpressure point.
- [ ] After the cache and queue measurements are actionable, reduce representative heavy-scene cost (currently roughly 2,000 draw calls and one million vertices per frame) through measured batching or redundant-state elimination without changing rendering correctness.
- [ ] Run a repeatable five-minute-or-longer A/B route from the same save with cold/warm phases and scene markers; use the performance summarizer to gate median, p95/p99, frames over 100/250 ms, and visual-baseline regressions.
- [x] Record the exact Pinyon Shift commit, ReXGlue commit, applied patch-set identity, source-payload identity, and executable hash in build metadata and structured diagnostics so future soak-test evidence is attributable to a reproducible build.

## Quick wins

These should fit in roughly half a focused day each, including a small automated
check. They intentionally avoid work already active in the soak-test and ReXGlue
0.10 migration branches.

- [x] Add a launcher **Reset runtime settings** action that backs up only
  `pinyon_shift.toml`, recreates the supported default configuration, and opens
  the backup location. This replaces the current troubleshooting instruction to
  delete the file manually without touching saves, cache, generated code, or the
  rest of `.local`.
- [x] Add a small `tools/summarize-performance.py` command for the per-frame CSV
  produced by the soak-test epic. Emit sample duration, median and p95 frame
  time, median FPS, 1% low, draw-call/stall totals, cache hit rates, and a compact
  JSON or Markdown comparison against one baseline run. Reject empty, truncated,
  or incompatible captures instead of reporting misleading numbers.
- [x] Add a checked-in allowlist for the three known code-generation warnings
  (`0x8241A370`, `0x82AD8138`, and `0x82AD813C`) and a log verifier that fails on
  any new warning signature. Keep the accepted entries documented rather than
  silently suppressing them, and re-baseline the allowlist once ReXGlue 0.10
  lands.
- [x] Add a safe graphics-experiment preset tool that backs up the host config
  and can select 4x/8x/16x anisotropic filtering plus `none`/`fxaa`/
  `fxaa_extreme`. Preserve the current defaults, reject unsupported values, and
  provide a one-command restore path; do not expose frame-rate or temporal
  upscaling flags through this tool.
- [x] Align CI and releases with the new `dev`/`main` branch model: run CI on
  pushes to `dev`, run the release-contract tests in the release workflow, and
  reject a release tag when `config/release.json` does not match the tag or the
  tagged commit is not contained in `main`.
- [x] Add a tracked-Markdown local-link checker to the asset-free CI suite so
  renamed docs, scripts, and source references fail before merge. Ignore web
  links and ignored/private research paths; validate only repository-relative
  targets that are meant to ship.

## Mid-size wins

These are bounded to about one focused engineer-day each after their listed
dependency is available. If an item grows beyond that boundary, split the
instrumentation or tool from the gameplay investigation instead of refactoring
unrelated systems.

- [x] Add an **Experimental graphics** section to the launcher for anisotropic
  filtering and FXAA, using the same validated settings as the preset tool.
  Include an explicit config-schema migration with backup, safe defaults, a
  reset button, restart-required messaging, diagnostics/support-bundle fields,
  and release-contract tests. Do not include resolution scaling in the first UI
  pass.
- [x] Build a visual-baseline helper that creates exact-build capture folders
  for front end, garage, daytime/night open world, traffic, race, rewind, and
  UI-heavy scenes. Generate a manifest plus side-by-side contact sheet from
  manually captured PNGs, and flag missing or mismatched scene labels. This is a
  lightweight oracle, not an automated pixel-perfect gameplay test.
- [x] After the graphics UI and visual-baseline helper are green, add **2x
  internal resolution** as an experimental, restart-required option with 1x as
  the recovery default. Use the performance summarizer and representative scene
  captures to enforce a documented GPU/memory budget before calling it
  supported.
- [x] Add a one-variable-at-a-time renderer A/B harness for
  `readback_memexport`, `clear_memory_page_state`, and
  `d3d12_submit_on_primary_buffer_end`. Keep shipping defaults unchanged; record
  the exact config and build fingerprint, and compare both performance and
  visual evidence. For the memexport test, first count exporting draws, bytes,
  synchronous fallbacks, and queue/fence waits so a speedup cannot hide lost
  guest-memory coherency. Exclude `vsync=false` because it changes guest vblank
  behavior rather than providing a valid FPS unlock.
- [x] Add a qualification-session command that creates a timestamped run
  manifest, records operator markers for cold boot, menu, race, save, clean
  exit, relaunch, and reload, then packages only the relevant logs, hashes, and
  results. It should make the existing manual admission gates repeatable without
  trying to automate gameplay input.
- [x] Add once-per-process SDK-stub reachability reporting: record the first hit
  for each stubbed import by module, symbol/address, and call count, then emit a
  bounded shutdown summary and include it in sanitized diagnostics. Use the
  results to prioritize the 99 stubbed imports by real gameplay reachability
  rather than raw inventory order.

## Explicitly deferred

Do not treat a frame-rate unlock, native renderer replacement, FSR2/FSR3,
ultrawide, HDR, or broad generated-source restructuring as a quick or mid-size
win. The readiness assessments classify those as multi-week or refactor-scale
projects that need stronger compatibility, visual, and performance oracles first.
