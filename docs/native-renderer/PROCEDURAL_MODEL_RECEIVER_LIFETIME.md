# Procedural-model receiver lifetime

This NR-05A milestone identifies the first semantic title receiver behind the
qualified indirect command-buffer lineage. It proves an engine class, its
object lifetime, its exact object extent, and two observed render-related
stages. Runtime evidence shows those stages are not universal prerequisites
for its render dispatch. Individual mesh/material meaning, LOD policy, and
streaming ownership remain unclassified.

## Static identity

The supported USA retail image proves this exact chain:

| Evidence | Address or value |
| --- | --- |
| Complete-object locator | `82363C9C` |
| Type descriptor | `832B9EDC` |
| Decorated RTTI name | `.?AVCProceduralModels@proceduralGeometry@@` |
| Reviewed class | `proceduralGeometry::CProceduralModels` |
| Vtable | `82002B5C` |
| Virtual dispatch slot | 41 |
| Dispatch function | `82417BC0` |
| Constructor | `82E1C9A0` |
| Destructor | `82E1CA28` |
| Scalar-deleting destructor | `82E1D9B0` |
| Array constructor | `82E1CDC8` |
| Object stride | 512 bytes |
| Visibility-preparation virtual | slot 14, `82E1FD00` |
| Render-state virtual | slot 40, `824170D8` |

The constructor calls its base constructor, writes vtable `82002B5C`, and
initializes the reviewed receiver fields before returning. The destructor
writes the same vtable, releases its owned fields, and calls its base
destructor. Vtable slot zero is the scalar-deleting destructor, which calls the
reviewed destructor before optional deallocation. Slot 41 is exactly
`82417BC0`.

This identity is separate from the already-proved command root. At dispatch
entry, receiver `r3` is the `CProceduralModels` instance while producer root
`r6 + 59712` is a different address. The implementation never labels that
command root as the procedural-model object.

## Preparation and payload layout

The array constructor advances exactly 512 bytes between constructed
`CProceduralModels` objects. Within the derived portion, static instruction
evidence proves these structural fields:

| Offset | Structural role |
| ---: | --- |
| 124 | descriptor-owner pointer |
| 128 | parallel runtime-record pointer |
| 132 | auxiliary allocation pointer |
| 136 | active/double-buffer index |
| 140 | runtime-record capacity |
| 320–383 | 64-byte transform/constant matrix |
| 384–447 | 64-byte transform/constant matrix |
| 448–511 | 64-byte transform/constant matrix |

Virtual slot 14 walks 92-byte descriptor records and parallel 68-byte runtime
records, performs the observed spatial/visibility tests, and writes the runtime
selection state. Virtual slot 40 publishes the three 64-byte matrix ranges and
invokes the per-record helper at `82417418`; slot 41 consumes the same record
strides while producing the already-qualified command lineage.

These are structural names, not claims about a shipping engine ABI. In
particular, the exact mesh, material, LOD, and streaming meaning of individual
record members is still unknown.

## Runtime lifetime join

Balanced constructor hooks retain entry `r3` and publish its address only
after the constructor returns. Balanced destructor hooks change that exact
address from live to destroying at entry and to destroyed at exit. A reused
address receives a monotonically increasing local generation.

The fixed 1,024-entry lifecycle table is lock-free on the hot dispatch path.
The `82417BC0` context hook accepts a semantic receiver only when its exact
entry `r3` address is currently live. Unregistered, destroying, destroyed,
overflowed, or zero-generation receivers remain unknown and are counted.
Each accepted address and generation then follows the existing exact
producer, owner, constructor, packet, nested-buffer, and prepared-draw chain.

Balanced hooks also bracket slot 14 and slot 40. A completed visibility call
increments a receiver-generation visibility epoch. A completed render-state
call records the visibility epoch it consumed and increments a render-state
epoch. Slot 41 snapshots all three values into the exact packet lineage.

The AppData capture proved that these are optional stage histories rather than
a universal two-step prerequisite for slot 41: only six of 73 active receivers
visited slot 40, and some valid dispatching receivers visited neither observed
stage. Qualification therefore fails closed on an unregistered generation,
an impossible epoch relationship, or an unbalanced stage stack, while
reporting dispatches before both stages as an observed alternate route. It
still requires at least one exact lineage that carries all three epochs so the
full stage join itself is proved. The raw lifecycle event retains the older
`with_preparation` field names for capture compatibility; report totals call
them dispatches after or before both observed stages.

Qualification requires balanced constructor and destructor stacks, exact
published/destroyed/live accounting, zero table overflow, zero unknown or
post-destruction dispatches, and at least one full-stage lineage carrying an
exact live receiver generation. Per-address lifecycle summaries reconcile
with the aggregate counters.

## AppData qualification

Release executable SHA-256
`714DB33D4C139E0E50767163CDB1FEFB6D9841A5599CEA114E461B88C016076D`
ran against the installed `0.1.0` preview save in session
`20260829T171002Z-p39732`. The saved festival scene rendered correctly and the
process exited cleanly after 7,983 measured frames (245.863 seconds).

The final fail-closed stage-history report is `complete`:

- 256 constructor entries and exits published 256 live generations;
- 127,396 semantic dispatches all joined an exact live generation;
- zero unregistered, destroying, destroyed, overflowed, unknown-stage, or
  stack-fault cases;
- 72,281 balanced visibility calls and 16,543 balanced render-state calls;
- 43,401 dispatches followed both observed stages, while 83,995 preserved the
  newly proved alternate-stage routes;
- no guest payload reads, guest state/control changes, or suppression.

Performance held a 30.228 FPS median with a 19.461 one-percent low, 49.526 ms
p95 frame time, 59.952 Hz presentation cadence, and zero present-deadline
misses. The captured gameplay frame is
`native-renderer-procedural-model-preparation-open-world.jpg` (SHA-256
`70492E7E9684401D05C55C4C9BB37CA9A69E3A99AAAE6719F4A43AD3BD87FD58`).

## Safety and remaining semantic work

The hooks observe registers only. They do not read the receiver or command-root
payload, mutate guest memory, alter control flow, issue a native draw, or
expose suppression. Xenos remains authoritative.

This milestone proves the class, receiver address generation, observed
construction-to-destruction interval, record strides, matrix ranges, and the
visibility/render-state stage histories. It does not prove which record
members own meshes or materials, which entries are world instances, the exact
LOD policy, or how streaming registration maps to destruction. Those remain
required before NR-05B semantic extraction.
