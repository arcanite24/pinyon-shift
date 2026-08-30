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

## Owner-class method inventory

The next correlation layer reads the owner vtable address already reachable
from each live vehicle object and snapshots exactly 32 method slots once when
an identity is first observed. The address and method snapshot must remain
stable for the identity. This bounded read is enabled only with the native
renderer census and never invokes a method or changes guest memory.

The vehicle-pose qualifier groups identical vtables into owner-class seeds.
`inventory-native-renderer-vehicle-vtables.py` then resolves every nonzero
method pointer through the local code-generator partition map and records its
generated source, body hash, direct callees, indirect-call count, tail calls,
and any existing Pinyon hook mentions. These are method candidates only. The
inventory explicitly does not label a method as rendering, classify the player
car, enable a native vehicle draw, or allow suppression.

The AppData-backed owner-class run `20260830T085521Z-p38092` captured 9,251
valid observations with no invalid values across the same 31 identities. All
identities shared vtable `8213BA54` and the exact 32-slot snapshot hash
`C12A0EBD48670E64`; no address or vtable mismatch occurred. All 30 unique
nonzero methods resolved to generated title functions. A bounded depth-12
static call graph reaches existing diagnostic hooks from 11 roots, but only
through the unrelated retain diagnostic or the already-known pose hook. Static
shape therefore did not prove a render method.

## Balanced owner-method correlation

Three deliberately broad candidates were instrumented with balanced entry and
sole-tail-return hooks: slots 14 (`82BCC368`), 20 (`82BD2DE0`), and 22
(`82BC8410`). Entry r3 is admitted as a vehicle owner only after it matches an
identity already captured by the pose census. While that exact scope is open,
the existing title-origin and backend-packet lineage can attach a draw without
changing either path.

The release/AppData run `20260830T090929Z-p4584` completed normally and
recorded 9,116 valid pose observations, 31 identities, no invalid observations,
overflow, stack fault, error, or fatal event. Slots 14 and 20 each made 24
balanced calls before any captured owner matched. Slot 22 made 9,492 balanced
calls, 9,092 on admitted vehicle owners, but enclosed zero title draw origins
and zero backend packet matches. This rejects all three as currently proved
vehicle render methods and identifies slot 22 as a high-frequency
update/presentation path.

The next bounded step observes slot 22's six exact virtual callsites
(`82BC8468`, `82BC84A4`, `82BC84DC`, `82BC8688`, `82BC86BC`, and `82BC86E4`)
only while an admitted vehicle-owner scope is active. Each target is grouped by
callsite, generated target, and component-object vtable. This is a downstream
component-dispatch seed, not a render identity: native drawing, publication,
and suppression remain disabled and Xenos remains authoritative.

The release/AppData run `20260830T091806Z-p37948` completed normally with
56,279 valid pose observations across 40 identities. It recorded 120,322 valid
downstream dispatch observations, five exact targets, and no invalid value,
overflow, owner-stack fault, error, or fatal event. The two high-frequency
targets (`82BA97D8` and `82BABA90`) each ran 56,246 times through component
vtable `82139774`; targets `82BA9CB0` and `82BA9FF8` each ran 2,610 times
through that same vtable, and target `82BA6FA0` ran 2,610 times through vtable
`82139B54`. The `82BC8468` callsite produced no admitted target.

All five targets resolve to tiny generated title functions with no direct or
indirect callees and no existing native-renderer hook reachable within the
bounded static call graph. This evidence further classifies slot 22 as a
component update/presentation dispatcher; it does not prove a vehicle render
method. Native vehicle rendering and suppression therefore remain closed.

Qualify a batched census with:

```powershell
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot $stateRoot `
  -Scene open_world_day

python .\tools\summarize-native-renderer-vehicle-pose.py `
  $eventLog `
  --output .local\qualification\native-renderer-vehicle-pose.json

python .\tools\inventory-native-renderer-vehicle-vtables.py `
  .local\qualification\native-renderer-vehicle-pose.json `
  --partition .local\generated\default\codegen.partition.json `
  --generated-root .local\generated\default `
  --output .local\qualification\native-renderer-vehicle-vtables.json
```
