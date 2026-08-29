# Exact-family fail-closed suppression

The first NR-04D implementation is deliberately narrower than whole-pass
suppression. For the qualified sky/horizon pair
`747837906D0BF484` / `1D253A52B55C9FB3`, it preserves the authoritative Xenos
anchor draw and conditionally omits only the adjacent follower draw.

The follower is omitted only after all of these conditions hold in the same
draw:

1. the restart-gated, default-off family CVar is explicitly enabled;
2. both exact signatures and their adjacency match;
3. the title eligibility gate rejects queries, memexport, resolved inputs,
   unsupported geometry, incomplete resource layouts, and binding overflow;
4. both isolated native draws were recorded into the retained target; and
5. the complete native color and depth/stencil pair was published into the
   exact guest targets.

NR-04E/NR-04F add a runtime state gate on top of those per-draw conditions.
Eight consecutive successful publication frames are required before the first
suppression. Any exact-family frame gap resets the warm-up; any replay or
publication failure executes Xenos and starts a 120-frame cooldown. See
[STATE_BASED_YIELD.md](STATE_BASED_YIELD.md).

The backend decides after publication, not before it. If replay is unavailable
or either attachment cannot be published, it executes the original follower
draw. It never suppresses the anchor, a resolve, query, event, fence, memexport
operation, or later consumer. This preserves a complete Xenos recovery path
without needing to reconstruct the earlier anchor state.

## Control and telemetry

The launcher setting is
`pinyon_shift_native_renderer_sky_horizon_suppression`. It defaults to `false`,
requires a restart, and automatically selects only the qualified signature
pair. Explicit incompatible diagnostic environment overrides fail closed with
`status=blocked_invalid_configuration`.

An armed run emits:

- `native_renderer.suppression_control` with
  `implementation=fail_closed_follower_draw`;
- per-attempt `native_renderer.retained_pass.publication` events that identify
  whether the follower was suppressed or the original fallback executed; and
- `native_renderer.suppression_summary` with attempts, suppressed followers,
  state-gated Xenos yields, fallbacks, cooldowns, unexpected suppressions, and
  the last matching frame/draw.

## Rollback qualification

`tools/qualify-native-renderer-rollback.py` accepts one enabled log and one
disabled log from the same executable. It requires normal shutdown in both,
complete publication with no fallback in the enabled route, positive follower
suppression, and zero suppressed followers after rollback. Its deterministic
output promotes only the `rollback_switch` gate.

The 2026-08-29 paired AppData qualification used executable
`2060C64808794C10B368350566542E2005646D9513B252391980D525732BC22A`.
Enabled session `20260829T092338Z-p31960` published and suppressed the exact
follower 5,442 times with zero publication failures or Xenos fallbacks, then
shut down normally. Disabled session `20260829T092551Z-p25116` used the same
executable, reported the control disabled, suppressed zero draws, and shut down
normally. Both runs reached the installed festival save with complete sky,
world geometry, crowds, vehicles, UI, and post-processing.

`tools/qualify-native-renderer-rollback.py` promoted `rollback_switch=pass`, so
the manifest now records `rollback_qualified=true` and suppression admission is
12/12 for this exact, operator-requested family. The feature remains
restart-gated and default-off.

The hardened PR build passed its enabled AppData state-yield qualification and
same-build rollback pair. Enabled session `20260829T095155Z-p3564` yielded 48
complete publications during warm-up and then suppressed 12,223 of 12,223
eligible followers with zero failures, fallbacks, cooldowns, or unexpected
suppressions. Disabled session `20260829T095601Z-p32088` suppressed zero draws.
The manifest therefore records `state_yield_qualified=true`.
