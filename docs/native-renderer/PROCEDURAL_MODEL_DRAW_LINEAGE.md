# Procedural-model draw lineage

This NR-05B investigation follows each accepted procedural-model semantic
submission through graphics virtual slot 160 to the physical `PM4_DRAW_INDX`
header consumed by the backend. The first checkpoint was a negative overlap
census against two unrelated `PM4_DRAW_INDX_2` constructors. The current
bridge hooks slot 160's own exact packet stores. Native upload, native draw,
and suppression remain disabled.

## Proven boundary

The per-record helper `82417418` has one balanced invocation scope:

- `8241741C` observes entry after the helper prologue;
- `82417B60` validates the resolved-resource and geometry tuple immediately
  before graphics virtual slot 160 is called;
- `82417B80` is the single converged epilogue after that call returns.

Static instruction flow proves the ordering. A bounded thread-local stack
carries receiver generation, record index, descriptor/runtime addresses, and
the 64-bit semantic submission key only for that invocation. The geometry
observer also reads the graphics object's vtable and its byte-160 method
pointer, adding eight bounded bytes to the submission census. Null, unaligned,
or inconsistent dispatch targets fail closed.

The existing packet provenance remains an overlap probe. Direct hooks
`82410328` and `829F7CB0` cover two exact `PM4_DRAW_INDX_2` constructors and
follow their physical packet headers to backend outcomes. If either constructor
runs inside a semantic item scope, it receives the exact semantic identity. No
identity is reconstructed from timing, global draw order, or a guessed guest
pointer.

The same scope also counts construction of the six already-proved indirect
packets at `824095B4`, `82416EFC`, `8246FC1C`, `8263BD64`, `829E8E88`, and
`829EC49C`. This establishes constructor overlap only. It does not assign an
entire indirect buffer, which may contain commands from other producers, to a
single semantic submission.

## What the consolidated runs proved and disproved

Release/AppData session `20260829T194535Z-p33004` observed 1,169,255 accepted
semantic submissions and the same number of exact item-scope joins. It observed
zero semantic origins at the two direct packet constructors. All 225,297 exact
backend matches from those constructors were again EDRAM-copy outcomes.

Therefore those constructors are not the direct slot-160 path in the captured
festival scene. Physical PM4 correlation is proved for packets they create,
but no physical packet or prepared draw signature is yet proved for a
procedural submission. The implementation and static contract record this as
a complete negative overlap result instead of promoting unrelated resolve
traffic to semantic lineage.

The expanded Release/AppData session `20260829T200406Z-p40560` then observed
1,024,289 accepted submissions across 819 exact semantic keys. Every submission
used graphics context `2E02E000`, vtable `8200306C`, and byte-160 method
`82415CE0`; no invalid dispatch target, scope mismatch, or accounting fault was
observed. Four tracked indirect-packet constructors ran within two semantic
scopes, while the other 1,024,287 scopes had no tracked indirect constructor.
This proves rare scope overlap, not buffer ownership or prepared-draw lineage.

Static inspection resolves `82415CE0` to a thin state/update wrapper around
`82415F68`. The callee emits PM4 words directly into the graphics context's
command stream through the packet sequence beginning at `824161EC`, and
updates the stream cursor at `82416350`. Its two branches construct
`PM4_DRAW_INDX` opcode `0x22` at exact header stores `82416260` and
`824162F4`. This explains why the two previously tracked direct constructors
saw no semantic origin: slot 160 is itself a distinct packet-emission path.

The current bridge observes those two stores before the title instruction
executes, computes only the effective guest packet address, translates it to
the physical address through the existing packet-provenance path, and attaches
the active semantic key and scope generation. Backend consumption still uses
the exact physical header address and oldest retained address generation. A
large submission may emit multiple packets, so packet counts may exceed scope
counts without weakening the join.

## Runtime accounting

The fail-closed report reconciles:

1. accepted submissions to exact render-item scopes;
2. scopes with and without direct or indirect tracked packet origins;
3. any captured direct origins to physical packets and backend outcomes;
4. exact entry = exit + shutdown-open scope accounting;
5. zero stack faults, identity mismatches, native admission, or suppression.

Run it with:

```powershell
python tools/summarize-native-renderer-semantic-draws.py `
  <diagnostic-jsonl> `
  --static <native-renderer-dispatch-static.json> `
  --session <session> `
  --output <semantic-draw-boundary.json>
```

A `complete` report means the scope, packet-generation, physical-address, and
backend accounting all reconcile. `physical_pm4_packet_correlation_proved`
requires every accepted scope to emit at least one exact tracked packet.
`prepared_draw_lineage_proved` additionally requires at least one prepared
backend outcome and no matched unprepared outcome. Both remain runtime gates,
not static assumptions.

## Qualification result

Release/AppData session `20260829T202741Z-p30324` cleared the physical-packet
and prepared-draw gates in one consolidated run. All 888,664 accepted semantic
scopes emitted an exact `82416260` or `824162F4` packet. The backend consumed
888,312 of those packet generations as prepared draws across 819 unique
signatures; zero matched packets were unprepared. The remaining 352 packet
generations were pending only at clean shutdown, and matched plus pending
exactly reconciles the 888,664 recorded origins.

Every match retained the same semantic receiver generation, record index, and
key. Address failures, provenance-table overflow, scope mismatches, stack
faults, backend-outcome mismatches, native admission, and suppression were
zero. The report therefore proves both
`physical_pm4_packet_correlation_proved` and
`prepared_draw_lineage_proved`. This establishes an exact passive bridge from
the procedural semantic submission to its physical PM4 header and prepared
Xenos draw; it does not yet establish the resource ABI needed for native
rendering.

The next NR-05B layer now uses that exact bridge to separate immutable prepared
templates from dynamic semantic instances and conservative batch groups. See
`SEMANTIC_INSTANCE_CATALOG.md`. Session `20260829T210122Z-p37672` proved the
compact catalog across 403,015 prepared associations, 900 composite templates,
and 1,067 conservative batch groups, with bounded layouts and zero hidden
template or resource variation. Native batching and admission remain disabled.

## Safety boundary

All observations are passive and bounded. The implementation does not alter
guest memory, title control flow, resource bindings, command buffers, draw
state, or backend submission. Xenos remains authoritative. Mesh/material ABI,
texture ownership, vertex/index formats, LOD meaning, streaming lifetime,
prepared signatures, and native batching eligibility remain unproved.

The saved visual checkpoint is
`.local/qualification/native-renderer-semantic-pm4-runtime.png`; the live
festival save rendered normally. Its 193.692-second capture measured 29.701
median FPS, 15.272 FPS one-percent low, 59.538 Hz presentation cadence, one
present-deadline miss, and zero XMA stalls. All semantic-submission,
semantic-instance, command-lineage, semantic-draw, and performance reports
completed from this single saved session; no confirmation rerun was required.
