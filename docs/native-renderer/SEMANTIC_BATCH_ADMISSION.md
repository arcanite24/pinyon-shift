# Semantic batch-admission census

This NR-05C measurement checkpoint turns the global semantic catalog into an
execution-order plan. It records only exact consecutive prepared draws and
never assumes that globally compatible groups may be reordered. The census is
passive: Xenos still executes every draw, and native upload, drawing, batching,
admission, and suppression remain disabled.

## Exact batch identity

One opportunity key combines:

- the immutable prepared-template key;
- decoded geometry- and texture-resource hashes;
- the title's primary and optional secondary resource keys;
- a bounded world-family mask that independently marks exact C1 track-world
  and exact C2 static-world lineage; and
- the fail-closed eligibility result.

The title resource keys travel with the already-proved semantic submission
identity into the physical `PM4_DRAW_INDX` join. They are not looked up again
from mutable guest state at backend time.

An executable run exists only while eligible draws with the same exact key are
adjacent in one frame. A frame boundary, rejected draw, or key transition
closes the run. Because the world-family mask is part of the key, a generic
procedural draw cannot extend an exact track/static run even when every GPU
resource happens to match. The census performs no front-to-back or material
reordering.

## Admission boundary

The first measured admission class is intentionally narrow. A draw must have:

- a nonzero title primary-resource key;
- opaque color writes with blending disabled;
- no resolved render-target input;
- no query/conditional behavior or memexport;
- bounded geometry with one supported vertex binding and a supported indexed
  or auto-index source;
- bounded texture layout with one to four fetches;
- no constant-observation overflow;
- a complete prepared vertex/pixel pipeline and the expected color/depth
  target coverage.

Every first failing predicate is counted by name. Rejected entries retain
their exact template/resource identity and remain on Xenos. Eligibility is a
measurement classification, not permission to upload, issue, or suppress a
draw.

## Measurements

For each exact opportunity the runtime records draw and frame coverage,
consecutive runs, multi-draw runs and their draw coverage, maximum run length,
and whether consecutive draws switch semantic instances or repeat the same
instance. The summary additionally records per-frame density and template,
geometry, texture, and title-resource transitions. Exact C1 and C2 group,
draw, and multi-draw-run totals are reconciled independently; they remain
measurement-only until runtime evidence proves a useful opportunity.

Projected command count is conservative:

```text
eligible consecutive runs + rejected Xenos draws
```

Potential reduction is the eligible draw count minus eligible consecutive
runs. It is not a performance claim; it is the upper bound for a future
order-preserving implementation with the current admission rules.

## Fail-closed report

Generate the report from the same diagnostic session and static dispatch
inventory used by the semantic catalog:

```powershell
python tools/summarize-native-renderer-semantic-batches.py `
  <diagnostic-jsonl> `
  --static <native-renderer-dispatch-static.json> `
  --session <session> `
  --output <semantic-batch-admission.json>
```

Schema `pinyon-shift.native-renderer-semantic-batch-admission.v4` requires:

- one armed provenance configuration and one batch summary;
- exact equality with the prepared semantic-contract call count;
- zero matched unprepared draws and zero opportunity-table overflow;
- entry, run, rejection, projected-command, and reduction accounting to
  reconcile exactly;
- exact world-family partitions to reconcile to the tagged opportunity groups;
- explicit Xenos authority with native execution and suppression disabled.

`conservative_batch_plan_proved` also requires at least one eligible draw, one
multi-draw run, and a nonzero order-preserving command reduction. Failure keeps
the plan unproved and does not change runtime rendering.

`track_world_batch_opportunity_proved` and
`static_world_batch_opportunity_proved` are stricter family-local signals. Each
requires an eligible tagged group with a multi-draw run; neither signal admits
an executor, culling, LOD selection, publication, or suppression.

## Qualification result

Release/AppData session `20260829T211909Z-p31988` exercised 2,839 frames of
live festival gameplay and classified 938,575 exact prepared semantic draws.
Of those, 635,197 passed the narrow admission predicates. The remaining
303,378 were rejected fail-closed: 166,953 for non-opaque state and 136,425
for resolved-render-target input. No opportunity-table overflow or accounting
fault occurred.

The exact executable-order result is decisive: all 635,197 eligible draws
formed single-draw runs. Maximum run length was one, multi-draw run coverage
was zero, and the projected command reduction was therefore zero. The report
correctly leaves `conservative_batch_plan_proved` false. This is not a runtime
failure; it proves that the full template/geometry/texture/title-resource key
is too specific to justify an executor in the observed scene.

The same session exited normally with Xenos authoritative and native upload,
draw, batch execution, reordering, admission, and suppression disabled. It
measured 29.725 median FPS, 15.151 FPS one-percent low, 59.986 Hz presentation,
and zero present-deadline misses. The rendered festival scene remained
visually intact. The admission report SHA-256 is
`D694D7683ABBD05B0D678BDB40A99EDA75FFE1F51AA9958A1428C39B411ABF3F`.
The saved progress image is
`.local/qualification/native-renderer-semantic-batch-progress.jpg`, SHA-256
`BAE6948F17E50F07B288B316C4E557AD2FE0858485F7658517FDC25C5C4E3971`.

## Next gate

Do not implement an executor for this exact grouping. First measure a safe
coarser equivalence boundary that separates immutable mesh/material state from
per-instance resource identity, or evaluate an order-preserving instancing
path that can carry per-draw parameters explicitly. Any later executor must
still retain per-item Xenos fallback and remain incapable of suppression until
paired visual and side-effect qualification passes.

The follow-up equivalence ladder now implements that measurement boundary.
It separates a resource-free pipeline identity from draw arguments, geometry,
textures, render targets, and shader-used constant values, then measures
mesh/material instancing, material reuse, and pipeline reuse independently.
See `SEMANTIC_BATCH_EQUIVALENCE.md`.

The measured material and pipeline opportunities feed a bounded shadow cache
without enabling native state objects or execution. See
`SEMANTIC_STATE_CACHE.md`.
