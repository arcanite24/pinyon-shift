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
- the title's latest exact LOD index observation and an explicit validity bit.

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
resource, prepared-signature, visibility-category, result-mask, and title-LOD
identities. A record without an observed title LOD remains a distinct candidate
with `title_lod_valid=false`; zero is never inferred to be a valid LOD.
The exact prepared signature prevents a resource family from merging a
replayable draw with a resolved-input or otherwise mechanically ineligible
variant. The runtime records:

- all semantic prepared observations;
- selected, rejected, and missing workset joins;
- fresh, stale, and future selected decisions;
- per-candidate draw/frame coverage and maximum policy age;
- exact shader identities, specialization masks, and isolated-draw mechanical
  eligibility;
- title-LOD-bearing candidate entries and draws, reconciled with the exact
  visibility-record workset lineage;
- the complete isolated-draw mechanical rejection mask for every ineligible
  entry, preserving simultaneous failures instead of reporting only the first;
- table occupancy, overflow, and complete partition accounting.

The `isolated_draw_v1` admission contract assigns independent bits to resolved
inputs, unsupported geometry, empty draws, vertex-layout/count faults, constant
or texture overflow, memexport, queries, texture count/layout, missing prepared
pipeline stages, and unsupported render-target binding. The offline report
decodes these masks into per-reason entry and draw totals. A zero mask is
required for `mechanically_eligible=true`; the reporter rejects any disagreement
or unknown bit. This telemetry diagnoses a gate but never bypasses it.

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

The normal checkpoint only carries host metadata. When an operator separately
arms an exact isolated-draw signature with the fresh-visibility gate, the table
can admit one private-target native replay through all existing mechanical
safety checks. A startup-only auto-selector may instead lock the first exact
signature that is both fresh and mechanically eligible, eliminating a separate
candidate-discovery run without weakening admission. It is incompatible with
retained-pass publication and suppression. The original Xenos draw and
displayed frame remain authoritative; this path cannot suppress Xenos. Without
an explicit exact-signature or auto-selection request, the table issues no
native work.

For NR-05D qualification, `-RequireTitleLodCandidate` adds a stricter
auto-selection gate. The candidate must carry an exact valid title LOD
observation through the same receiver-generation and record identity; missing
LOD lineage waits for a later candidate and cannot lock a signature. This gate
is valid only with `-AutoSelectFreshVisibilityCandidate`, is startup-only, and
does not infer LOD zero. The lock event records the exact LOD index while Xenos
remains authoritative.

### Bounded workset shadow replay

After one exact-signature candidate has proved the replay boundary, the
default-off `-VisibilityShadowReplay` census mode exercises the broader
visibility-selected workset without locking one signature. It accepts only a
prepared draw that is mechanically eligible, carries a current or one-frame-
old independent visibility selection, and has exact semantic PM4 provenance.
At most the first such candidate in each frame is replayed into a private
target; later eligible candidates in that frame are counted as quota yields.

Exact title LOD remains bounded metadata rather than an admission predicate.
Runtime evidence showed that the mechanically replayable category-11 draws do
not execute either title LOD write hook, while exact-LOD category-9 draws fail
the independent mechanical replay contract. Requiring both therefore produced
an empty intersection. The workset replay records explicit LOD values when the
title wrote one and separately accounts requests without LOD; it never infers
LOD zero.

The mode keeps a fixed 256-signature request table with first/last frame,
request count, exact title-LOD observations, missing-LOD requests, and the
observed LOD range when one exists. Shutdown telemetry partitions every
prepared observation into mechanical rejection, stale/unselected rejection,
per-frame quota yield, or native replay request. Every request is reconciled
both by LOD evidence and as recorded, target-creation failure, or unsupported.
Any table overflow or incomplete accounting fails the evidence report.

This mode adds no readback, native publication, draw suppression, or guest
state mutation. Each native draw is discarded with its private target and the
original Xenos draw executes normally. It is mutually exclusive with exact
isolated capture, retained-pass replay/publication, and suppression. The
capture wrapper also arms dispatch discovery because admission requires
exact semantic PM4 provenance. Runtime configuration fails closed when that
provenance is unavailable rather than reporting a healthy zero-draw session.
Capture a batched AppData session with:

```powershell
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot $stateRoot `
  -Scene open_world_day `
  -VisibilityShadowReplay

python .\tools\summarize-native-renderer-visibility-shadow-replay.py `
  $eventLog `
  --output `
    .local\qualification\native-renderer-visibility-shadow-replay.json
```

The resulting signature coverage and outcome accounting determine whether the
qualified one-draw path generalizes across the selected procedural workset;
they do not admit publication or suppression.

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

Release/AppData session `20260830T081921Z-p13044` qualified the bounded
workset replay itself. It recorded all 25 requested private native draws across
two exact prepared signatures, with zero target-creation failures, unsupported
draws, signature overflow, error events, or fatal events. Selection accounting
partitioned 3,978,187 prepared observations into 3,662,084 mechanical
rejections, 316,078 stale/unselected exclusions, and 25 requests. All requests
lacked a title LOD because their category-11 title path executed no LOD write;
that absence was explicitly reconciled without inferring an index. The game
loaded the installed AppData festival save and remained visually stable.
Native output stayed private, the original Xenos draws remained authoritative,
and publication and suppression stayed disabled.
