# Vehicle-instance semantic seed

NR-05E starts from the title's vehicle-pose stream at `82BC5A3C`. Runtime
qualification proved that this boundary is shared by the player car, traffic,
and other live vehicle instances; it must not be described as player-only. The
boundary resolves each active vehicle slot and the exact position and
forward-vector addresses consumed by the title. The native renderer receives
the same already-read values through a read-only host observation, performs no
additional guest read, and cannot modify title state.

The census identity is the exact tuple of title generation, source object,
owner object, and active slot. A fixed 64-entry table records transform
addresses, observation and motion counts, frame span, maximum position delta,
and whether the optional presentation stabilizer supplied an effective pose.
An address change within one identity is a qualification failure rather than a
silent update. Shutdown emits every captured identity, and qualification fails
on overflow, truncation, invalid values, or incomplete accounting.

This is a vehicle-instance semantic seed, not vehicle draw identity or a
player-car classifier. It establishes the per-instance transform and lifetime
boundary needed to correlate later vehicle render submissions. Player priority
remains explicitly unadmitted until a separate title-semantic discriminator is
proved. The census does not identify materials, wheels, suspension, traffic
classes, reflection inputs, or a suppressible draw family. Native upload,
native drawing, publication, and suppression remain disabled; Xenos stays
authoritative.

## Qualification evidence

The AppData-backed `open_world_day` run
`20260830T083911Z-p9532` completed normally with the release executable. It
recorded 15,587 valid observations and no invalid observations across 31 exact
vehicle identities. Twenty identities changed position, all 31 changed their
forward vector, transform addresses remained stable, the 64-entry table did
not overflow, and the log contained no error- or fatal-like events. The
machine-readable report is generated locally at
`.local/qualification/native-renderer-vehicle-pose-20260830-pr139.json`.

This evidence proves only the read-only vehicle-instance transform boundary.
It does not prove which identity is the player car or correlate any identity
to a draw.

Qualify a batched census with:

```powershell
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot $stateRoot `
  -Scene open_world_day

python .\tools\summarize-native-renderer-vehicle-pose.py `
  $eventLog `
  --output .local\qualification\native-renderer-vehicle-pose.json
```
