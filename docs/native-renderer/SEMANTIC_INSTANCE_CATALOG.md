# Procedural-model semantic instance catalog

This NR-05B checkpoint converts the proved procedural submission-to-prepared-
draw lineage into a compact, fail-closed catalog. It separates immutable draw
templates, dynamic resource instances, and conservative batch groups without
uploading or drawing anything natively. Xenos remains authoritative for every
entry.

## Three exact identities

The catalog joins three independently bounded runtime records:

1. The semantic-instance key identifies one live
   `CProceduralModels` receiver generation and record index. It retains the
   first descriptor, runtime, and transform hashes plus explicit variation
   counts.
2. The semantic-submission key adds the resolved primary and optional
   secondary resource chains, state family, runtime submission object, count,
   source address, and exact graphics dispatch target.
3. The prepared template key is a composite hash of the prepared pipeline,
   shader/specialization pair, vertex declaration, texture instruction layout,
   render-state layout, and primitive/index metadata reached through the exact
   physical `PM4_DRAW_INDX` header generation. The backend candidate signature
   remains a separate correlation identity because one signature can cover
   multiple immutable layouts.

The report rejects a submission unless its receiver generation and record
index join exactly to one immutable semantic-instance record. It rejects a
prepared association unless its nonzero template key retains one exact
immutable identity. The prepared signature must still match the backend
signature independently.

## Template and resource split

Each prepared association records bounded hashes and the scalar fields needed
to audit the split:

- prepared pipeline, vertex and pixel shader, and specialization masks;
- guest primitive, source selection, indexed mode, index format, and
  endianness;
- vertex-binding and vertex-attribute layout;
- texture fetch/instruction layout and layout-valid mask;
- render-state layout without dynamic constant values;
- index, vertex, and texture resource identities separately from the layout;
- minimum and maximum observed index count;
- explicit template and resource variation counters.

The immutable template excludes guest resource addresses and dynamic constant
values. The dynamic instance retains the semantic record hashes and the exact
geometry, texture, and title resource identities. A conservative batch key is
the tuple of template key, geometry-resource hash, texture-resource hash, and
the primary/secondary title resource keys.

An association is batchable only when geometry and texture layouts are
bounded and neither its template nor its resource identity varied inside the
aggregate. A non-batchable association remains in the catalog with its reason
visible; it never falls through to an inferred identity.

## Fail-closed report

Run the existing lineage report after the semantic-instance and submission
summaries have been emitted:

```powershell
python tools/summarize-native-renderer-semantic-draws.py `
  <diagnostic-jsonl> `
  --static <native-renderer-dispatch-static.json> `
  --session <session> `
  --output <semantic-draw-catalog.json>
```

Schema `pinyon-shift.native-renderer-semantic-draw-catalog.v4` publishes:

- exact submission-to-draw associations;
- immutable prepared templates;
- joined dynamic semantic instances;
- conservative batch groups and batchable call coverage;
- physical-packet, prepared-draw, and compact-catalog gates.

`compact_semantic_catalog_proved` requires complete prepared lineage, one
contract for every prepared semantic draw, bounded geometry and texture
layouts, and zero template or resource variation hidden by aggregation. A
failed catalog gate does not weaken the already-proved PM4 lineage; it keeps
the affected entries on Xenos and provides the next classification target.

## Safety boundary

This checkpoint observes decoded backend metadata that already exists for the
prepared Xenos draw. It performs no additional guest payload reads, writes no
guest memory, uploads no native resource, issues no native draw, enables no
native batch, and suppresses no Xenos work. Native admission remains false
even for a stable, bounded batch group.

## AppData qualification

Release executable SHA-256
`F506BD779EEC86E36A91C175002ADE299818E268EE5EAA2476B29914D2E19314`
ran the installed `0.1.0` preview save in session
`20260829T210122Z-p37672`. The save loaded into live festival gameplay and the
process exited normally after 2,906 measured frames (101.369 seconds).

The submission, semantic-instance, command-lineage, semantic-catalog, and
performance reports all completed from that one session. The catalog proves:

- 403,325 accepted semantic submissions across 842 submission keys and 447
  immutable instance keys;
- 403,015 exact prepared associations across 820 backend signatures and 900
  composite immutable templates;
- 1,067 conservative batch groups covering all 403,015 prepared calls;
- all prepared calls had bounded geometry and texture layouts, stable template
  identity, and stable resource identity, with zero hidden variation;
- 310 packet generations remained pending only at clean shutdown, while zero
  matched packets were unprepared;
- physical PM4 correlation, prepared-draw lineage, and the compact semantic
  catalog gate are all proved;
- Xenos remained authoritative, with no native upload, native draw, native
  batching, guest-state change, or suppression.

Performance held 29.672 median FPS, 15.266 FPS one-percent low, 59.959 Hz
presentation cadence, zero present-deadline misses, and zero XMA stalls. No
crash, fatal error, device loss, assertion failure, or unexpected shutdown was
found in the logs. The catalog report SHA-256 is
`6828395FDF838BB66146AD43F7E32331310F64858C5DA982B2FDFDBC12726040`.
The live 3072x1728 screenshot is
`.local/qualification/native-renderer-semantic-instance-catalog-progress.png`,
SHA-256
`F792181CBF2A11251259D1F54A79F0F22CE0161098FAEE6643BC0E5007AF1941`.

The next NR-05C checkpoint converts these global groups into a conservative
execution-order census. It admits only exact consecutive opaque prepared draws
within one frame, records every rejection reason, and measures projected
command reduction without issuing native work. See
`SEMANTIC_BATCH_ADMISSION.md`.

Session `20260829T211909Z-p31988` completed that census and found no adjacent
multi-draw runs under the exact full-resource identity. An executor remains
deferred pending a safely coarser equivalence boundary.
