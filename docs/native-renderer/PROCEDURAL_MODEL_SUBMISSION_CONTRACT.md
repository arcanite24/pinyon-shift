# Procedural-model submission contract

This NR-05B slice classifies the exact resolved-resource, structural
state-variant, and geometry-submission boundary at the end of the per-record
`proceduralGeometry::CProceduralModels` helper. It does not identify a title
material or mesh ABI and does not render natively. Xenos remains authoritative
for every observed submission.

## Exact title boundary

Helper `82417418` keeps the live receiver in `r27`, the descriptor record in
`r28`, the parallel runtime record in `r26`, the graphics context in `r31`, and
the resource-lookup context in `r20`.

The static inventory proves ten observation points:

| Hook | Structural operation |
| --- | --- |
| `82417A74` | bind descriptor word 0's receiver-table key to slot 0 |
| `82417A9C` | conditionally bind descriptor word 4's key to slot 1 |
| `82415B64` | observe the opaque provider returned by lookup `82410A58` |
| `82415B80` | observe the provider byte-24 predicate result |
| `82415BA4` | observe the provider byte-44 fallback predicate result |
| `82415BC0` | observe the selected byte-36 or byte-40 method result |
| `82415BE4` | observe the opaque secondary-resolution result |
| `82415C50` | observe the opaque object returned by resolver `82415AD0` |
| `82415C6C` | prove that exact object reaches graphics virtual slot 88 |
| `82417B60` | submit the runtime object and geometry source tuple |

For each resource binding, the descriptor word is multiplied by the
receiver-table stride of eight, added to the table at receiver offset 8, and
passed to helper `82415BF8`. That helper accepts a binding slot below five,
caches the resource key, resolves it through `82415AD0`, and calls the graphics
context's virtual slot at byte offset 88. The observed uses are exactly slots
0 and 1. Its first cache is a five-key array at `834AD4CC`, indexed by
graphics binding slot:
an unchanged key skips both resolution and rebinding, so the runtime preserves
the previously dispatched object and provenance for that exact binding slot.

Resolver `82415AD0` owns a five-entry cache shared across binding roles. Each
12-byte entry contains bound object, resource key, and usage count at offsets
0, 4, and 8. On a cache miss it calls `82410A58`, which indexes the lookup
context's byte-2812 table with the pointed-to key and returns an opaque
provider. The resolver then follows one of these exact structural routes:

- provider predicate byte 24 succeeds, then provider method byte 36 runs;
- byte 24 declines and predicate byte 44 succeeds, then method byte 40 runs;
- byte 44 also declines, so no provider method runs.

A null selected-method result and the declined-provider path both call opaque
secondary-resolution function `823E58D8`. The final result is stored in the
selected cache entry and returned to the binding helper. The static proof does
not assign class, allocation, texture, material, or lifetime semantics to that
secondary function.

The runtime maintains a separate mirror for each title cache. The binding-
helper mirror is indexed by graphics binding slot and reconciled against the
exact guest key at `834AD4CC + slot * 4` before deciding whether the shared
helper will skip resolution. The resolver mirror is keyed by the exact guest
resolver-cache slot address and searched by resource key. A key can therefore
cross primary and secondary binding roles only with
the provider, route, object source, and final bound-object identity previously
proved at a bind dispatch. Resolver misses and protocol discontinuities remain
explicit failures.

The same helper also proves two structural partitions without assigning a
material ABI. Descriptor kinds form `kind_4_5`, `kind_1_3`, and `other` groups.
Helper state selects one of five table families: state 9 at offsets 4/28,
state 11 at 196/220, states 24-27 at 148/172, states 6-8 at 100/124, and all
remaining values at 52/76. Each accepted submission records the exact pair.

The same record then submits runtime word 0 through graphics-context virtual
slot 124. Virtual slot 160 receives primitive 13, byte count
`runtime_count_units * 4`, and one of two exact sources:

- the default path has zero count and uses runtime byte offset 24;
- the counted path reads its count at runtime byte offset 28 and source address
  at runtime byte offset 32.

The runtime census also retains the graphics object's vtable and exact method
pointer at byte offset 160. These are structural resource keys, binding slots,
an opaque runtime submission object, a geometry source tuple, and a dispatch
target. Exact provider and virtual-method identities are retained structurally,
but exact texture/material class,
vertex format, index format, mesh ownership, and streaming lifetime are still
open.

The first passive draw layer proved that an accepted tuple does not overlap the
two previously tracked `PM4_DRAW_INDX_2` constructors. Runtime target identity
then resolved slot 160 through `82415CE0` to emitter `82415F68`. Static decoding
proves that emitter's two `PM4_DRAW_INDX` header stores at `82416260` and
`824162F4`; the next bridge attaches the active semantic key to those exact
physical packet headers. See
`docs/native-renderer/PROCEDURAL_MODEL_DRAW_LINEAGE.md`. Backend prepared-draw
qualification, mesh/material ABI, and native eligibility remain separate
runtime gates.

## Bounded runtime join

The resource hooks retain only the pending receiver, descriptor/runtime
record addresses, graphics and lookup contexts, binding keys, exact opaque
provider/vtable/method identities, selected provider route, object source,
bound objects, and which slots were observed. The geometry hook consumes that
pending tuple and accepts it
only when all of the following hold:

- the receiver has an exact live constructor generation;
- descriptor and runtime addresses resolve to the same in-range record index;
- the receiver owner, record bases, count, and resource table are aligned and
  bounded;
- descriptor resource indices reproduce the keys observed at the binding
  helper;
- each required key joins to a nonzero opaque object observed at virtual bind
  slot 88, either directly or through the exact key cache;
- each nonzero object retains a nonzero provider, vtable, all four proved
  method identities, a primary/fallback/unavailable route, and either the
  selected provider method or opaque secondary resolution as its exact source;
- secondary binding presence exactly follows descriptor word 4's signed
  sentinel;
- runtime object, count, and source reproduce one of the two proved geometry
  source paths;
- the graphics context has a nonzero aligned vtable and nonzero aligned method
  pointer at byte offset 160.

Each accepted geometry observation reads 60 bytes, or 64 bytes when the optional
secondary resource is present. The extra eight bytes are the graphics vtable
and byte-160 submission method. A fixed 8,192-entry table aggregates exact
receiver generation, record, key/provider/vtable/method/route/source/object
chain, state-variant pair, runtime-object, geometry-source, and dispatch-target
tuples. A direct
non-null provider lookup reads 20 additional bounded metadata bytes: one
provider vtable pointer and four vtable method pointers. Mismatches remain
separately accountable and fail qualification.

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
accounting. It also reconciles lookup outcomes, provider selections and null
results, secondary-resolution outcomes, final resolver successes/misses, and
the 20-byte provider metadata budget. Unknown receivers, mismatched bindings,
invalid or unresolved resource joins, resolver misses, bind-protocol faults,
invalid geometry or dispatch targets, capacity overflow, native admission, or
suppression claims make it incomplete.

## Safety boundary

The hooks read bounded scalar fields and never modify guest state, redirect
title control flow, upload resources, issue host draws, or suppress Xenos
work. Every accepted tuple is classified as
`resolved_resource_state_variant_and_dispatch_submission` and retains
`xenos_replay`.

## AppData qualification

Release executable SHA-256
`902C2694E66BA1F929DE308BEC870B94C99AD5D6E6212A04E228931B9A720881`
ran against the installed `0.1.0` preview save in session
`20260829T192106Z-p37612`. The save loaded into the live festival world and
the process exited normally after 3,540 measured frames (129.354 seconds).

The provider-chain, semantic-instance, and command-lineage reports are all
`complete`:

- all 695,696 geometry submissions joined to an exact bound object and
  provider chain while retaining Xenos replay;
- 599,423 resolver/bind operations comprised 422,946 shared resolver-cache
  hits and 176,477 direct provider lookups; another 96,273 calls used the
  binding helper's exact per-slot key cache;
- 164,879 direct lookups selected provider method byte 36, while 11,598 took
  the declined-provider route and succeeded through opaque secondary
  resolution; the byte-40 fallback route was not observed;
- 34 unique provider chains covered every retained resource pair;
- zero lookup/resolution misses, null provider-method results, unresolved
  resources, protocol faults, bad joins, overflow, native admission, or
  suppression;
- 754,656 immutable semantic-instance observations and 8,114,562 prepared
  draws retained complete fallback and lineage accounting.

Performance measured 29.334 median FPS with an 18.902 FPS one-percent low,
50.990 ms p95 frame time, 59.983 Hz presentation cadence, zero present-
deadline misses, and zero XMA stalls. The semantic-submission report SHA-256
is `E6A8C430EA771DE44ED09ADC72CF30C77C5BDBCE589AB956E3D28157B6B83821`.
The 3072x1728 live screenshot is
`native-renderer-provider-chain-open-world.jpg`, SHA-256
`9C0168C242FE85E09C39B523A85B4487F55B6D187E2093A00B8300BC54A41657`.

## Previous resolved-object baseline

Release executable SHA-256
`87B00D70EEDED7DC0547C4F8E848AB754FD597EBBF0DECC652415E985AF19C57`
ran against the installed `0.1.0` preview save in session
`20260829T182827Z-p37932`. The save loaded into the live festival world and
the process exited normally after 8,897 measured frames (297.503 seconds).

The resolved-submission, semantic-instance, and command-lineage reports are
all `complete`:

- 910,008 geometry submissions joined exactly to a nonzero opaque primary
  bound object and retained Xenos replay;
- 784,056 resolver results reached graphics virtual slot 88 exactly, while
  125,952 bindings used a previously proved exact-key cache identity;
- zero resolver misses, bind-protocol faults, unresolved resources, unknown
  receivers, binding mismatches, invalid record/resource/geometry joins,
  table overflow, or native admission;
- 862 retained submission tuples covered 34 exact key/object resource pairs;
- descriptor groups covered 625,495 `other`, 218,733 `kind_4_5`, and 65,780
  `kind_1_3` submissions;
- helper-state coverage reached the default, state 9, state 11, and state
  24-27 table families; states 6-8 were not observed in this scene;
- 987,056 immutable semantic-instance observations and 11,057,773 prepared
  draws retained complete fallback and lineage accounting.

Performance held a 30.012 FPS median with a 19.198 FPS one-percent low,
50.764 ms p95 frame time, 59.986 Hz presentation cadence, zero present-
deadline misses, and zero XMA stalls. The semantic-submission report SHA-256
is `E2147F2363EC5054E5BA2F818F3BDD842D302E064D58DEF470131AA38D9A70FC`.
The live festival screenshot is
`native-renderer-procedural-material-state-open-world.png`, SHA-256
`B21B0FDDE371392514AC23CD480FC11B8AC6949C9D737A16F503233CECD24E11`.

## Previous structural baseline

Release executable SHA-256
`1614FEDFE718D182620187AF5CF9C3FD0E5E8AEA3663ED08A2122B59547417B0`
ran against the installed `0.1.0` preview save in session
`20260829T180132Z-p42336`. The save loaded into the festival world and the
process exited normally after 9,584 measured frames (297.300 seconds).

Before resolved-object and state-family instrumentation was added, the
semantic-submission, semantic-instance, and command-lineage reports were all
`complete` for the structural key/geometry contract:

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
