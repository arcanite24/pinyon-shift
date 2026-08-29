# State-based Xenos yield

NR-04E/NR-04F harden the exact sky/horizon suppression family without
admitting another family or suppressing any additional command type. The
restart-gated launcher switch remains default-off. When enabled, suppression
starts in a warming state and the original Xenos follower remains
authoritative until eight consecutive frames publish a complete native color
and depth/stencil pair.

The runtime state machine is:

| State | Native publication | Xenos follower |
| --- | --- | --- |
| `warming` | attempted and observed | executed |
| `active` | required before suppression | suppressed only after success |
| `cooldown` | attempted for recovery evidence | executed |
| `disabled` | unchanged diagnostic behavior | executed |

The transition from `warming` to `active` applies on the following frame, so
the publication that completes warm-up still executes the Xenos follower. A
gap in exact-family frames immediately resets warm-up and yields to Xenos. A
replay or publication failure enters a 120-frame cooldown, executes the
original follower, and requires a fresh warm-up before suppression can resume.

This gate changes only the follower draw decision. PM4 parsing, queries,
events, fences, memexport, resolves, and later consumers remain unchanged. The
anchor draw is always preserved and resolve suppression remains unavailable.
An unexpected backend suppression while the state machine yielded is recorded
separately and fails qualification.

## Qualification

`tools/qualify-native-renderer-state-yield.py` consumes one enabled AppData
session. It requires a warm-up-to-active transition, positive yielded draws,
complete publication, active suppression with no fallback, zero cooldowns,
zero unexpected suppressions, normal shutdown, and preserved guest side
effects. The manifest keeps `state_yield_qualified=false` until that runtime
qualification passes for the PR build.

The same build must also pass the enabled/disabled rollback qualifier. These
two reports together prove that the new runtime gate yields to Xenos before
confidence is established and that the operator can still fully disable the
experimental suppression route.

## AppData evidence

The 2026-08-29 PR build produced executable
`0D35FDBA928E4A1315A9B3C508272E6796010D033796108264CA6063D2F2334A`.
Enabled session `20260829T095155Z-p3564` yielded 48 complete publications to
Xenos during warm-up, transitioned from `warming` to `active`, and then
suppressed 12,223 of 12,223 eligible followers. It recorded zero publication
failures, Xenos fallbacks, cooldowns, or unexpected suppressions and shut down
normally after reaching the installed festival save.

Disabled session `20260829T095601Z-p32088` used the same executable, suppressed
zero draws, and shut down normally. Both the state-yield qualifier and the
same-build rollback qualifier passed, so the manifest now records
`state_yield_qualified=true`. Visual evidence is stored locally at
`.local/qualification/native-renderer-state-yield-enabled-20260829.jpg`.
