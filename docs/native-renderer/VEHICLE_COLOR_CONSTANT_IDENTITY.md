# Vehicle color constant identity census

Status: implemented as a default-off, measurement-only extension of the
qualified vehicle shadow/color correlation; runtime evidence is batched with
the next C4 AppData session.

## Purpose

The retained color pass proves that 30 exact geometry families can form one
coherent vehicle contribution. It does not connect that contribution to one of
the title-owned live vehicle identities or expose the render transform used by
the color shaders.

The next bounded join compares only the already-observed vertex float
constants of each correlated color draw with the latest title-owned vehicle
poses. It tests every finite three-component constant vector against:

- the position of every vehicle identity no more than one frame old; and
- both signs of every fresh vehicle forward vector.

Position and forward use the same tight squared-delta limits as the earlier
typed matrix census: `0.25` and `0.04`, respectively. The observer never reads
new guest memory and does not persist constant values.

## Evidence contract

Every correlated draw produces exactly one position outcome and one forward
outcome:

- `unique` means exactly one constant-register/identity pair passed the tight
  threshold;
- `ambiguous` means more than one pair passed; and
- `miss` means none passed, including the explicit no-fresh-pose case.

Each of the 30 exact color families retains its last unique identity and
constant register plus identity/register variation counts. A family is a
stable tight position candidate only when every observation is unique and the
identity and register never change. The offline qualifier promotes a complete
shared vehicle-transform candidate only when all 30 families meet that rule
and name the same title generation, owner, and slot.

That result would prove a vehicle-instance transform bridge, not that the
instance is the human player's car. A separate title-semantic discriminator is
still required before applying the player label. Ambiguous or missing results
select the next typed constant-upload investigation rather than widening
heuristic object scans.

## Safety boundary

- The census is active only with the existing default-off shadow geometry
  correlation mode.
- Constant payloads are neither logged nor written to reports.
- No native draw, publication, or suppression decision depends on a match.
- Every authoritative Xenos draw remains present.
- Missing, stale, non-finite, or ambiguous evidence cannot establish identity.

Qualify it with the existing retained-pass batch command in
[`VEHICLE_RETAINED_COLOR_PASS.md`](VEHICLE_RETAINED_COLOR_PASS.md). The v7
vehicle report requires full scan/outcome accounting and exposes
`complete_shared_vehicle_transform_candidate` without changing
`object_identity_proven` or `native_admission_allowed`.
