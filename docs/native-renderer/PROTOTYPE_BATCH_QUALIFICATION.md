# Native prototype batched qualification

Phase B6 is qualified as an early, manually testable native prototype. A clean
build and an AppData-backed `comparison_native` run displayed a recognizable,
stable world slice with current-frame native authority. Xenos draws remained
enabled, suppression remained disabled, and unsupported startup or replay work
fell back to the complete Xenos output.

This checkpoint is not native scene parity. The displayed native slice includes
sky and atmosphere, a ground or road surface, horizon structures, and integrated
lighting and shadow behavior. It remains visibly low-resolution and does not
yet contain the vehicle, HUD, detailed world and props, transparency, or the
complete effects chain. Those are Phase C and D work.

## Build identity

The repository prepared all 102 ReXGlue patches from a clean clone and built the
preview successfully:

- patch-set SHA-256:
  `9D3DF3A2560A4F5DF9AA00E992FA759BAD42494711324BBC90E0D57FEE38EFF5`;
- `pinyon_shift.exe` SHA-256:
  `33AA2B330582F0E1AD84488D332C957C4488112E47DB4C7D43E498DF4EED1C89`;
- `rexgpu-xenos.dll` SHA-256:
  `99E92B1D18EF838AAF005B4B0DBBA8142B268D21301194DC665AFE0DBD8E2C39`;
  and
- ReXGlue commit `f5337cdc947ff6d4c4196737e2c807a48f2a1fc2`.

The last lifecycle change separates the D3D12 backing resource dimensions from
the effective logical draw dimensions. The command processor derives a bounded
logical width and height from the active viewport and scissor, carries them
through active, deferred, and committed retained state, and uses them for the
prototype crop. D3D resource operations continue to use the physical backing.
The observed pairs were `512x288` logical in `640x8192` backing at 2x and
`256x144` logical in `320x4096` backing at 1x.

## AppData gameplay evidence

Session `20260830T223753Z-p38480` used the installed 0.1.0 preview state root
and its existing profile through `tools/launch-preview.ps1`. The temporary
qualification settings selected shipping 1x, `comparison_native`, FXAA,
16x anisotropy, and disabled blur and depth-of-field. The original graphics
configuration was restored after normal shutdown.

The process exited normally with code 0. Logs contain no runtime fatal, crash,
device loss, device removal, D3D validation error, or unintended suppression
signature. Nine sampled native-output markers had exact matching frame and
retained-frame identifiers, native authority, preserved Xenos draws, and
disabled suppression. Three waiting markers retained Xenos fallback safely.

The payload-free continuous-workset report records:

- 10,295,899 prepared observations and 16,892 replay requests;
- 16,868 recorded requests, including 16,854 qualified retained-family seeds;
- 14,083 target-reuse requests;
- 2,785 complete frames and 24 accounted target-creation fallback frames;
- zero unsupported outcomes and zero fail-closed yields; and
- independently proven multi-draw accumulation, swap-committed freshness, and
  clean Xenos fallback.

The exact shadow observer recorded 2,768 complete 80-draw batches: all 221,440
draws recorded successfully, all 2,768 publications completed, and no producer,
backend, target, or publication failure was observed.

The game naturally autosaved the active profile during the run. Its resulting
file was 51,208 bytes with SHA-256
`1D1932BA49679C11A5D0962B49A91505041CF9E6F6FDB1D5ACE9C393519D3B70`.
The launcher and qualification workflow did not copy, move, reset, overwrite,
or otherwise manipulate the save.

## Observed timing

The session contained 3,305 samples over 134.979 seconds. These values describe
one prototype run and are not performance claims:

- median derived FPS: 28.465;
- one-percent-low FPS: 14.587;
- presentation, simulation, and vblank cadence: 58.987, 29.575, and 60.002 Hz;
- presentation deadline misses: 0;
- mean guest-frame GPU time: 33,791.990 microseconds;
- mean native-composition GPU time: 49.731 microseconds; and
- mean native-selection GPU time: 8.905 microseconds.

The run recorded 70 dropped and 4,727 duplicate presents. These counters and
the low-resolution partial output remain baseline evidence for later parity and
performance work, not a regression judgment.

## Failure investigation and closure

Four AppData sessions narrowed and closed the retained-frame lifecycle defect:

- `p44068` exposed a crash caused by sharing the color-preview and depth-only
  replay target lifetime;
- `p45032` remained stable after separating those targets but exposed stale
  retained-state reporting;
- `p33228` isolated the remaining mismatch: a `320x4096` 1x backing resource
  was being compared with a fixed `512x288` logical scene; and
- `p38480` passed after logical extent became draw-derived and retained through
  publication.

The qualifier schema is now version 2. It accepts only accounted fail-closed
fallback frames, requires at least three increasing exact native-output markers,
and verifies that every waiting marker preserves Xenos authority with
suppression disabled. It therefore distinguishes safe fallback from native
success without rejecting a healthy prototype merely because startup or an
unsupported frame yielded to Xenos.

## Gate decision

B6 passes the early-prototype gate: the supported gameplay scene visibly and
continuously reaches the final displayed frame, missing work remains safe under
Xenos fallback, and the result launches normally without capture tooling.

The default remains `xenos`; all prototype selectors remain restart-gated;
guest draws, resolves, queries, fences, memexport, and other side effects remain
preserved; and suppression is not allowed. Phase C must now replace the partial
retained family with semantic terrain, road, static-world, vehicle, sky,
vegetation, transparency, and effects coverage before this can be described as
a complete native gameplay renderer.
