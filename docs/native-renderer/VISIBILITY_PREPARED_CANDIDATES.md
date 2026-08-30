# Visibility-selected prepared candidates

The native visibility workset is produced at the title's slot-14 record
completion boundary. The semantic-instance helper at `8241741C` is an upstream
superset, so a workset join there is not yet evidence that a record reached a
prepared graphics draw. This checkpoint carries the independent selection
through the already-qualified semantic submission lineage without changing
the title or issuing native work.

## Exact handoff

The semantic-instance scope copies the latest workset result into its immutable
draw identity:

- receiver address, receiver generation, and record index;
- selected, rejected, or missing workset result;
- policy frame, visibility category, and predicted category-result mask.

That identity already follows the title's submission at `82417B60` into the
physical `PM4_DRAW_INDX` stores at `82416260` and `824162F4`. The backend joins
the exact physical header address and address generation to its prepared draw.
No timing, FIFO, signature-only, or global-order attribution is accepted.

At the prepared boundary, only an independently selected decision whose policy
frame is the current frame or the immediately preceding frame becomes a host
candidate. A selected decision older than one frame is stale and excluded. A
prepared frame earlier than its policy frame is a causality fault. Rejected and
missing workset results are expected fail-closed exclusions from the semantic
superset.

## Bounded evidence

Fresh candidates are aggregated in a fixed 4,096-entry table keyed by exact
semantic identity plus immutable prepared template, geometry-resource, texture-
resource, visibility-category, and result-mask identities. The runtime records:

- all semantic prepared observations;
- selected, rejected, and missing workset joins;
- fresh, stale, and future selected decisions;
- per-candidate draw/frame coverage and maximum policy age;
- table occupancy, overflow, and complete partition accounting.

Generate and qualify the evidence with:

```powershell
python tools/discover-native-renderer-dispatch.py `
  .local/generated/default `
  --image .local/analysis/default-image.bin `
  --output .local/qualification/native-renderer-visibility-lineage-static.json

python tools/summarize-native-renderer-visibility-prepared-candidates.py `
  <diagnostic-jsonl> `
  --static .local/qualification/native-renderer-visibility-lineage-static.json `
  --session <session> `
  --output .local/qualification/native-renderer-visibility-prepared-candidates.json
```

Qualification requires exact accounting, at least one fresh prepared
candidate, zero future decisions, and zero table overflow. Stale, rejected, and
missing observations remain measured exclusions and never enter the candidate
table.

## Safety boundary

This checkpoint only carries host metadata. It writes no guest state, changes
no title control flow, uploads no resource, issues no native draw, and cannot
suppress Xenos. Xenos remains the sole rendering authority. The candidate
table is an admission input for a later native consumer, not permission to draw
or suppress by itself.

## AppData qualification

Release session `20260830T015106Z-p25800` ran against the installed `0.1.0`
preview save and exited normally. It partitioned 363,948 exact semantic
prepared observations into 9,921 selected joins, 33,390 rejected exclusions,
and 320,637 missing-workset exclusions. Of the selected joins, 8,561 were
current- or one-frame-old candidates retained across 13 exact entries and
1,360 were stale exclusions. Future decisions and table overflow were zero.

The prepared-candidate, workset, every visibility shadow, semantic instance,
semantic submission, semantic draw, semantic batch, and command-lineage
reports all completed from the same capture. Median performance was 29.750 FPS
over 2,802 frames, with a 15.224 FPS one-percent low, 58.633 Hz presentation,
and zero present-deadline misses. The fatal-signature scan was clean. Native
upload, native draw, and suppression remained disabled throughout.
