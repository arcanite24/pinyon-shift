# Procedural-model submission contract

This NR-05B slice classifies the exact structural resource-binding and
geometry-submission boundary at the end of the per-record
`proceduralGeometry::CProceduralModels` helper. It does not identify a title
material or mesh ABI and does not render natively. Xenos remains authoritative
for every observed submission.

## Exact title boundary

Helper `82417418` keeps the live receiver in `r27`, the descriptor record in
`r28`, the parallel runtime record in `r26`, the graphics context in `r31`, and
the resource-lookup context in `r20`.

The static inventory proves three observation points:

| Hook | Structural operation |
| --- | --- |
| `82417A74` | bind descriptor word 0's receiver-table key to slot 0 |
| `82417A9C` | conditionally bind descriptor word 4's key to slot 1 |
| `82417B60` | submit the runtime object and geometry source tuple |

For each resource binding, the descriptor word is multiplied by the
receiver-table stride of eight, added to the table at receiver offset 8, and
passed to helper `82415BF8`. That helper accepts a binding slot below five,
caches the resource key, resolves it through `82415AD0`, and calls the graphics
context's virtual slot at byte offset 88. The observed uses are exactly slots
0 and 1.

The same record then submits runtime word 0 through graphics-context virtual
slot 124. Virtual slot 160 receives primitive 13, byte count
`runtime_count_units * 4`, and one of two exact sources:

- the default path has zero count and uses runtime byte offset 24;
- the counted path reads its count at runtime byte offset 28 and source address
  at runtime byte offset 32.

These are structural resource keys, binding slots, an opaque runtime
submission object, and a geometry source tuple. Exact texture/material class,
vertex format, index format, mesh ownership, and streaming lifetime are still
open.

## Bounded runtime join

The two resource hooks retain only the pending receiver, descriptor/runtime
record addresses, graphics and lookup contexts, binding keys, and which slots
were observed. The geometry hook consumes that pending tuple and accepts it
only when all of the following hold:

- the receiver has an exact live constructor generation;
- descriptor and runtime addresses resolve to the same in-range record index;
- the receiver owner, record bases, count, and resource table are aligned and
  bounded;
- descriptor resource indices reproduce the keys observed at the binding
  helper;
- secondary binding presence exactly follows descriptor word 4's signed
  sentinel;
- runtime object, count, and source reproduce one of the two proved geometry
  source paths.

Each accepted observation reads 52 bytes, or 56 bytes when the optional
secondary resource is present. A fixed 8,192-entry table aggregates exact
receiver generation, record, resource, runtime-object, and geometry-source
tuples. Mismatches remain separately accountable and fail qualification.

The runtime emits `semantic_submission_entry` records and one
`semantic_submission_summary`. Validate them with:

```powershell
python tools/summarize-native-renderer-semantic-submissions.py `
  <diagnostic-jsonl> `
  --static <native-renderer-dispatch-static.json> `
  --session <session> `
  --output <semantic-submission-report.json>
```

The report requires complete observation, binding, payload, entry, and replay
accounting. Unknown receivers, mismatched bindings, invalid record/resource
joins, invalid geometry, capacity overflow, native admission, or suppression
claims make it incomplete.

## Safety boundary

The hooks read bounded scalar fields and never modify guest state, redirect
title control flow, upload resources, issue host draws, or suppress Xenos
work. Every accepted tuple is classified as
`structural_resource_and_geometry_submission` and retains `xenos_replay`.

## AppData qualification

Release executable SHA-256
`1614FEDFE718D182620187AF5CF9C3FD0E5E8AEA3663ED08A2122B59547417B0`
ran against the installed `0.1.0` preview save in session
`20260829T180132Z-p42336`. The save loaded into the festival world and the
process exited normally after 9,584 measured frames (297.300 seconds).

The semantic-submission, semantic-instance, and command-lineage reports are
all `complete`:

- 463,613 geometry submissions joined exactly to their primary binding;
- all 463,613 retained Xenos replay, with zero native admissions;
- zero unknown receivers, binding mismatches, invalid record/resource joins,
  invalid geometry, or table overflow;
- 24,107,876 bytes reconciled exactly across the 52/56-byte bounded payloads;
- 605 exact structural tuples covered 21 resource-key pairs;
- 425,753 submissions used the offset-24 default source and 37,860 used the
  offset-28 count plus offset-32 source;
- descriptor kinds 0, 4, 1, and 5 accounted for 318,565, 111,424, 33,604, and
  20 submissions;
- 502,877 semantic-instance observations and 6,128,088 prepared draws retained
  complete fallback/lineage accounting.

Performance held a 30.215 FPS median with a 19.480 FPS one-percent low,
48.743 ms p95 frame time, 59.987 Hz presentation cadence, zero present-
deadline misses, and zero XMA stalls. The semantic-submission report SHA-256
is `B2DEED99ACE5CCB075581A20CDBC7656C07E19A6E690FC150429988DFEB752EC`.
