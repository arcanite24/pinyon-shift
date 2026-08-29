# Title draw provenance

This NR-05A bridge connects a title-level draw caller to the exact backend draw
without relying on thread timing, global FIFO position, resolution, or
shader-only heuristics. When that draw reaches pipeline preparation, the bridge
also records the exact prepared signature. It remains passive and default-off.
Xenos still parses and executes every packet, and no result produced here
permits suppression.

## Why a FIFO is insufficient

The title writes command buffers on a guest CPU thread while ReXGlue decodes
them later on the graphics command-processor thread. A wrapper invocation and
the next prepared draw are therefore not a safe pair: indirect buffers,
direct packet-wrapper callers, predication, unsupported packets, or a draw
that does not reach pipeline preparation can shift either sequence.

The bridge instead uses the identity already shared by both sides: the
physical address of the stored PM4 header.

## Exact correlation path

1. The entry hook on `0x824079B8` retains the adapter caller `LR` and unchanged
   `r3-r10` metadata in thread-local host state.
2. The indexed-wrapper hook at `0x8240F4DC` proves the forwarding edge when its
   caller is `0x824079FC`; direct indexed-wrapper callers retain their own LR.
3. Immediately before the original header store at `0x82410328`, the packet
   hook records `physical(r3 + 4)`. The original `stwu` still executes.
4. The immediate wrapper uses the same contract at its header store
   `0x829F7CB0`.
5. ReXGlue patch `0080` records the physical address of every packet before
   decoding it and includes that address in `GraphicsDrawObservation`.
6. The draw observer consumes title metadata only when the two physical packet
   addresses match exactly. Reused live addresses retain each submission and
   are consumed oldest-first for that exact address. This is a per-address
   generation rule, not attribution to the next global draw.
7. The synchronous prepared-draw callback adds the existing exact prepared
   signature. ReXGlue patch `0081` then reports the exact `IssueDraw` return
   outcome for the same frame, draw, and packet identity. A missing outcome
   callback fails closed instead of silently treating the draw as unprepared.

This preserves direct evidence across producer/consumer threads without
serializing guest payloads or modifying the command stream.

## Object/context leads

The static dispatch inventory now records a bounded syntactic definition for
each `r3-r10` argument at every direct adapter callsite. It scans backward only
to the nearest intervening call, reports entry registers and call-clobbered
unknowns explicitly, and decodes simple memory loads into base register,
offset, and width. The runtime provenance report joins that record with the
observed argument variation and exact prepared signature.

This deliberately is not interprocedural dataflow. A stable `r3`, a load such
as `lwz r3,40(r31)`, or a narrow numeric range is only an object/context lead.
It does not establish pointerness, type, ownership, registration, destruction,
or lifetime.

The current deterministic MS-2505 inventory covers all 38 direct adapter
callsites: 288 of 304 argument slots have a bounded local definition, 16 stop
as unknown at an intervening call, and 32 are direct `lwz` field loads with an
explicit base register and offset. Runtime evidence is still required to
select which of these callsites owns a recurring prepared family.

## Bounded failure model

The outstanding packet table has 16,384 fixed entries. Provenance is aggregated
into 4,096 fixed `(outcome, origin wrapper, caller LR, backend signature)`
entries. Each aggregate retains first and last `r3-r10`, per-register numeric
bounds, and a variation mask. Prepared outcomes use the exact prepared
signature; unprepared outcomes use the existing draw signature. This is a
bounded lead for distinguishing stable owner/context candidates from per-draw
inputs; it is not proof that any value is a valid object pointer or that its
numeric range represents a lifetime.
The summary keeps separate counts for:

- title packets recorded and exact backend matches;
- matched packets whose draw never reached prepared-pipeline observation;
- packets still outstanding at shutdown;
- physical-address translation failures;
- live packet-address reuse handled by ordered per-address generations;
- packet-table and aggregate overflow;
- bounded per-thread origin-stack overflow or a packet hook with no origin;
- adapter-to-indexed forwarding mismatches; and
- backend draws that have no instrumented title packet, which is expected for
  unreviewed constructors and is not treated as an attribution.

Address translation, table/stack/aggregate overflow, forwarding, or origin
faults leave the deterministic report `status=incomplete_fail_closed`. A
nonzero pending count at clean shutdown is valid only when the exact accounting
identity `recorded = matched + pending` holds. Live address reuse is diagnostic,
not a fault, because every generation is retained. Unmatched data is never
assigned to the next caller or signature.

## Deterministic report

Generate the static inventory and run the existing AppData capture once at the
milestone boundary:

```powershell
$stateRoot = Join-Path $env:LOCALAPPDATA `
    'PinyonShift\source\0.1.0\.local\preview'
.\tools\capture-native-renderer-dispatch.ps1 `
    -StateRoot $stateRoot `
    -Scene open_world `
    -StaticOutput .local\qualification\native-dispatch-static.json
```

After clean exit, build the exact provenance report from that same diagnostics
stream:

```powershell
python .\tools\summarize-native-renderer-title-provenance.py `
    <diagnostics.jsonl> `
    --static .local\qualification\native-dispatch-static.json `
    --output .local\qualification\native-title-provenance.json
```

Milestone session `20260829T123251Z-p12356` closed with complete exact
accounting: 107,560 title packets recorded, 107,455 exact backend matches, and
105 packets still outstanding at clean shutdown. Forty live same-address
generations were retained and consumed without loss. The 107,455 matched draws
formed 66 statically joined unprepared aggregates, with zero address,
forwarding, origin, table, stack, or aggregate faults. No matched title draw
reached the prepared callback in this scene, so `prepared_coverage` correctly
remains `none_observed` and no semantic promotion follows from this capture.

## Exact backend outcome contract

ReXGlue patch `0081` closes the remaining ambiguity after an exact packet
match. D3D12 now emits one passive outcome for every `IssueDraw` exit. The
bounded vocabulary distinguishes completed and prepared work from EDRAM copy,
missing shader, zero-pitch, no-effect rasterization, zero host vertices,
pipeline-pending, and explicit backend failure paths. Each observation carries
the same frame, draw, and physical packet identity as the pre-submit draw
observation.

Pinyon consumes an unprepared candidate only when all three identities match.
Prepared outcomes must arrive after the synchronous prepared callback has
already consumed that candidate. Missing, duplicate, out-of-order, or
identity-mismatched outcomes are fail-closed accounting faults. The report
emits backend-wide outcome totals and exact title-match totals, and includes
the outcome in every unprepared caller/signature aggregate. None of these
outcomes permits draw suppression or changes Xenos execution.

Milestone session `20260829T125853Z-p38524` qualified this outcome contract
over 5,878 frames and 8,478,174 backend draw attempts. The backend reported
8,216,916 completed draws, 261,210 EDRAM copies, and 48
`no_rasterization_or_memexport` exits. All 132,568 exact title matches were
EDRAM copies. Outcome identity had zero mismatches and zero missing callbacks;
110 title packets remained validly pending at clean shutdown. This establishes
why the observed title path did not reach prepared-pipeline callbacks without
promoting it to a semantic render-object boundary.

The report recognizes only the two prepared signatures already qualified by
independent visual evidence: retained sky/horizon anchor
`747837906D0BF484` and follower `1D253A52B55C9FB3`. Every other signature
remains `unknown`. Even a known signature has `native_coverage=false` and
`suppression_eligible=false`; an unprepared outcome always remains semantically
unknown. This bridge proves dispatch provenance, not
object lifetime, material ownership, transforms, LOD, visibility, streaming,
destruction, or a semantic replacement boundary.

## Promotion gate

A caller may become an NR-05 semantic extraction hook only after repeated
scene captures reproduce its exact signature association and title-side
analysis proves the owning object and lifetime contract. Terrain/roads and
static world retain priority over the already-known sky family. This bridge
supplies the dispatch-to-draw evidence needed to investigate those owners; it
does not reorder the NR-05 priority list.
