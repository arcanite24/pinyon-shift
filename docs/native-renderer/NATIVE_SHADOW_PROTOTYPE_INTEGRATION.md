# Native shadow prototype integration

Phase B4 promotes the already qualified 80-draw, 2048-square dynamic-vehicle
shadow epoch into the normal native and hybrid prototype paths. Selecting
either prototype now arms the required bounded draw/provenance observers and
the shadow producer automatically; hidden census or capture settings are not
required.

The exact producer contract remains unchanged: 64 primary, 12 secondary, and
four tertiary depth-only draws must arrive in their capture-proven order on the
same D24S8 attachment. The native replay accumulates those draws in a private
target while every Xenos producer still executes. After draw 80, ReXGlue copies
only the complete private depth/stencil allocation into the matching
authoritative target before the existing Xenos render-target dump consumes it.
The dump and all later title sampling remain unchanged.

This is current-frame ownership, not a static shadow cache. Each exact epoch is
replayed and published independently. A sequence gap, backend replay failure,
target mismatch, non-monotonic frame, or publication failure permanently
closes native shadow publication for the process. The authoritative Xenos
producer and consumer chain remains active, so the prototype frame continues
with `shadow=fallback_xenos_failed_closed` rather than failing as a whole.
Frames where the exact epoch is simply absent report
`shadow=fallback_xenos_unavailable`.

## Safety boundary

- The published resource is the exact D24S8 allocation already consumed by
  the qualified `xenos_rt_dump_retained` handoff.
- Publication requires all 80 ordered draws and the complete matching target.
- No color attachment is accepted or modified.
- Xenos draws, render-target dump, later sampling, queries, fences, and
  resolves remain enabled.
- No draw or resolve suppression is introduced.
- Capture readback stays optional and is not enabled by the prototype.

The native and Xenos shadow payloads were byte-identical in the prior one-shot
and eight-epoch qualifications. This checkpoint reuses that proven path but
does not claim new visual or performance qualification; those checks remain in
the batched Phase B6 run.

## Diagnostics

Prototype output markers report one of:

- `shadow=native_current_frame` after an exact same-frame publication;
- `shadow=fallback_xenos_unavailable` before or outside a qualified epoch; or
- `shadow=fallback_xenos_failed_closed` after the first unsafe transition.

They also report `shadow_consumer=xenos_rt_dump_retained`. Shadow publication
events retain the exact frame, draw, target dimensions, caster class, atlas
region, publication epoch, preserved Xenos stages, and suppression-disabled
contract.
