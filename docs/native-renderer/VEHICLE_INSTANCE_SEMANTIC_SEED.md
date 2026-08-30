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

## Exact draw-argument correlation

The next join checks every exact title/backend draw against the already
captured vehicle owner, position, and forward-vector addresses. It covers the
direct wrapper arguments and semantic receiver, descriptor, and runtime, plus
the indirect constructor, owner, producer, context, context root, and semantic
receiver lineage. Each candidate would retain the exact backend signature,
provenance function and return address, argument index, vehicle identity, and
frame span. A fixed address index and fixed 1,024-entry result table keep this
discovery path bounded. No guest payload is read and no draw is changed.

Release/AppData session `20260830T093251Z-p42128` completed normally at the
festival and found no exact match, but later audit proved title provenance was
disabled for that run. Its 83,516,951 probes qualify only the indirect lineage;
they do not support the original direct-coverage claim.

The follow-up samples a single bounded relationship edge from object-like
dispatch roots: direct and indirect r3, semantic receiver/descriptor/runtime,
and indirect context roots. Each unique backend-signature, root, and 300-frame
window scans only the first 128 words (512 bytes), with a fixed 16,384-entry
cache and 2,048-entry correlation table.

Release/AppData session `20260830T094228Z-p1080` completed normally and
examined 2,282,451 backend draws. It reduced 7,424,713 eligible requests to
5,992 unique object scans (766,976 words) across 31 vehicle identities and
found zero embedded owner, position, or forward-vector addresses. This run was
also indirect-only and is retained as bounded partial evidence.

The corrected release/AppData session `20260830T094940Z-p26892` explicitly
armed title provenance. It covered 205,181 direct title draws, 505,770 semantic
probes, and 2,053,311 indirect draws across 31 vehicle identities. It found
zero exact or one-hop owner/position/forward matches. The pose, identity index,
scan cache, and correlation tables had no invalid observation, overflow, or
stack fault, and the log had no error or fatal event. This fully rejects the
current direct, semantic, and indirect arguments and the first 512 bytes of
their object-like roots. Follow typed descriptor graph edges or locate another
submission family; native vehicle drawing and suppression remain closed.

## Statically targeted render-context arguments

The next relationship layer is derived from generated title instructions
rather than address-shape heuristics. Function `824365B0` preserves guest `r7`
as an object, loads its first word as a vtable, loads virtual slot 8, and calls
that target. The same function consumes guest `r8` directly as vector source
data. Those exact arguments are therefore admitted to the existing bounded
512-byte one-hop correlation cache in addition to each provenance family's
original `r3` root. They may bypass the generic `0x40000000`–`0x6fffffff`
address-shape heuristic, but still require a nonzero aligned value and a
readable guest page range before the snapshot is copied. Separate request and
unique-scan counters prove both arguments were exercised by a qualification
session.

A broader experimental child scan was rejected before publication: guest
object lifetime can change between a page-access check and a payload read, and
common floating-point bit patterns occupy the same numeric range as guest
addresses. The retained path never dereferences a candidate child and makes no
type claim from its numeric value. It reads only the already-bounded root
snapshot, keeps Xenos authoritative, and leaves native vehicle drawing and
suppression closed until an exact owner, position, or forward-vector join is
proved.

Release/AppData session `20260830T103151Z-p43600` qualified the targeted
slice in stable festival gameplay. Both arguments were present outside the
generic address band: `r7` produced 692,963 scan requests and 3,660 unique
cache entries, while `r8` produced 692,963 requests and 424 unique entries.
The session covered 2,483,488 indirect draws and 31 vehicle identities with
complete provenance, zero overflow, no error or fatal event, and a normal
exit. Neither root contained an exact owner, position, or forward-vector join
within the bounded snapshot, so both are rejected for this relationship depth.
Continue from a typed callee contract or another submission family; native
vehicle drawing and suppression remain closed.

## Typed render-context callee profiles

Static caller tracing shows `82436468` forwards its guest `r8` and `r9` as
`824365B0:r7,r8`. Inside `824365B0`, modes `r6 = 0`, `1`, or `2` execute the
virtual call through `r7` slot 8 before consuming `r7 + 4`, `r7 + 16`, and the
32-byte vector source at `r8`. A read-only entry probe now captures that exact
typed contract while both arguments are live. It groups observations by the
resolved `r7` vtable and slot-8 target, records field and address churn, and
fingerprints the vector payload without retaining guest bytes.

An upstream hook at `82436468` also records the original caller return address
for context-path dispatches (`r10 != 0`) and matches its `r8/r9` pair to the
callee's `r7/r8` pair. The caller address participates in the profile key, so
one dynamic type shared by several submission families remains partitioned by
its exact origin. Missing or mismatched dispatcher lineage fails the report.

This is the deliberately narrow typed edge that follows the rejected broad
child scan. It reads only the statically proven root, nine vtable words needed
to resolve slot 8, and eight vector words after guest page-range checks. Invalid
root, vtable, and vector ranges have separate counters; missing coverage,
accounting drift, invalid reads, or profile overflow fail qualification. The
probe remains diagnostic-only: it uploads and draws nothing, leaves Xenos
authoritative, and cannot enable suppression.

Release/AppData session `20260830T104844Z-p14556` qualified 366,786 eligible
callee observations with 366,786 exact dispatcher matches, no invalid root,
vtable, or vector range, no mismatch, and no overflow. Two caller families
were present: `8240ECAC` contributed 80,224 observations and `8243AC64`
contributed 286,562. Both resolve vtable `820019CC` slot 8 to the single title
function `8243BC80`.

Static inspection classifies `8243BC80` as a boolean visibility/predicate
wrapper rather than a transform provider. It first calls the same object's
vtable slot 5; if that predicate is false and `r7 + 4` is non-null, it calls
the child object's slot 14 and returns that boolean. This precisely explains
the live `r7` contract but does not establish vehicle identity or a native draw
source. Continue from the now-partitioned caller families or the typed child
predicate edge; native vehicle drawing and suppression remain closed.

Qualify a batched census with:

```powershell
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot $stateRoot `
  -Scene open_world_day `
  -VehicleDrawCorrelation

python .\tools\summarize-native-renderer-vehicle-pose.py `
  $eventLog `
  --output .local\qualification\native-renderer-vehicle-pose.json

python .\tools\inventory-native-renderer-vehicle-vtables.py `
  .local\qualification\native-renderer-vehicle-pose.json `
  --partition .local\generated\default\codegen.partition.json `
  --generated-root .local\generated\default `
  --output .local\qualification\native-renderer-vehicle-vtables.json
```
