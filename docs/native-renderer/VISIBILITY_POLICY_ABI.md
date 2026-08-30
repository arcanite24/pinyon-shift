# Visibility policy ABI candidates

The first NR-05D runtime census proves the title's visibility and LOD outcomes.
This checkpoint narrows the inputs that produce those outcomes without naming
an unproven camera, frustum, or bounds layout.

## Proven structural flow

The slot-14 function preserves its second and third arguments, then partitions
both by title category:

| Input | Structural use | Evidence |
| --- | --- | --- |
| receiver `+4` | shared spatial context | vectors loaded at `+16` and `+32` |
| argument `r4` | category spatial table | `category * 192`; scalars at `+160`, `+164`, `+168` |
| argument `r5` | category query table | `category * 32` before helper dispatch |
| descriptor `+60` | squared-distance comparison scalar | compared against the shared `f26` value |
| runtime `+44` | earlier squared-distance threshold | compared against the same `f26` value |

The shared context vectors feed a clamp/subtract/vector-sum sequence whose
result is retained in `f26`. The category query reaches helpers `0x8243F9A0`
and `0x82441048` before record iteration. These derivations and exact
instructions are now part of static discovery, so binary or recompilation drift
fails closed.

The first helper interpolates between the two vector arguments, forms a
three-component squared delta, and delegates to `0x8243FD70`. That predicate
loads a query vector at offset 0 plus scalars at offsets 16, 20, and 24, then
compares scaled squared distances. The second helper loads six 16-byte vector
blocks at offsets 0 through 80, combines vector comparisons for both input
endpoints, and returns only 0, 1, or 2. Static discovery now proves those exact
structures as well as their callsites.

## Deliberately unproven semantics

The arithmetic is consistent with point-to-box squared distance and the helper
pair is consistent with spatial/frustum policy, but those names are not yet an
ABI contract. We have not proved:

- which shared-context vector is minimum, maximum, eye, or focus position;
- a camera or frustum-plane layout;
- whether the category scalars are extents, margins, ranges, or mode data;
- the descriptor/runtime scalar units or all category-specific branches.

The helper shapes strengthen the segment-distance and six-vector-classifier
hypotheses, but do not by themselves prove world-space units or that the six
vectors are camera frustum planes.

Accordingly this checkpoint enables only a future passive input/outcome
correlation census. Native policy execution, native culling, native LOD, guest
state mutation, draw suppression, and Xenos replacement remain disabled.

## Passive input/outcome correlation

That census is now implemented at three register-only boundaries:

| Boundary | Address | Captured title value |
| --- | --- | --- |
| record entry | `0x82E20094` | shared squared spatial value in `f26` |
| runtime-scalar comparison | `0x82E20134` | `f26` versus squared runtime `+44` scalar in `f0` |
| descriptor-scalar comparison | `0x82E201B0` | `f26` versus scaled-and-squared descriptor `+60` scalar in `f0` |

Every completed record joins those observations to its title outcome and
category. A bounded 256-bin IEEE-754 exponent histogram preserves the spatial
value distribution separately for early rejection, evaluated rejection, and
selection without logging raw per-object values. Per-category summaries retain
threshold reach and comparison counts. Non-finite/negative inputs, duplicate or
orphan threshold hooks, category drift, histogram drift, or any native-policy
flag fail qualification closed.

Generate the static contract and the runtime report with:

```powershell
python tools/discover-native-renderer-dispatch.py `
  .local/generated/default `
  --image .local/analysis/default-image.bin `
  --output .local/qualification/native-renderer-visibility-policy-static.json

python tools/summarize-native-renderer-visibility-policy.py `
  <diagnostic-jsonl> `
  --static .local/qualification/native-renderer-visibility-policy-static.json `
  --output .local/qualification/native-renderer-visibility-policy.json
```

## Runtime qualification

The consolidated AppData-backed Release capture
`20260829T230622Z-p39648` completed normally. It correlated 1,768,409 record
outcomes and the same number of spatial samples, including 1,694,229 early
rejections, 60,660 evaluated rejections, and 13,520 selections. All threshold
hooks joined to an open record. Duplicate hooks, orphan hooks, lifecycle and
identity faults, category and histogram overflow, and invalid spatial or
threshold values were all zero.

The capture also observed both comparison boundaries in meaningful numbers:
1,687,112 runtime-threshold observations and 334,276 descriptor-threshold
observations. Median performance was 30.195 FPS over 8,034 frames, with no
present-deadline misses and a normal exit.

This qualifies the passive structural input/outcome contract for semantic
hypothesis testing. It still does not prove camera, frustum, bounds, or unit
semantics, and it does not enable native policy execution.

## Ordered helper oracle

The next passive checkpoint traces the title's two proved helper returns at
their exact slot-14 callsites:

| Return boundary | Address | Captured value |
| --- | --- | --- |
| candidate-threshold comparison | `0x82E20258` | candidate scalar in `f0` versus the title's zero reference in `f29` |
| local squared-distance comparison | `0x82E202D8` | local squared distance in `f31` versus the squared candidate threshold in `f0` |
| spatial helper return | `0x82E20350` | low-byte boolean result from `0x8243F9A0` |
| six-vector helper return | `0x82E20368` | result 0, 1, or 2 from `0x82441048` |

The trace is ordered within the active title record. It counts candidate
threshold tests, local squared-distance tests, repeated spatial-helper tests,
subsequent six-vector classifications, and every pass/result by title category
and final title outcome. Accounting requires every local-distance test to
follow a non-negative candidate threshold, every spatial helper to follow a
local-distance pass, every classifier call to follow a spatial-helper pass,
every classifier result to remain in the statically proved 0/1/2 domain, and
all records to reconcile with the authoritative visibility census.

ReXGlue may invoke a registered interior continuation without the entry hook's
thread-local record scope. Those observations are counted explicitly as
unscoped continuations and excluded from the oracle dataset; they are not
treated as record-order faults. Qualification remains strict inside every
active authoritative record, where orphaned or out-of-order gates and invalid
values still fail closed.

This creates a title-oracle dataset suitable for a later shadow policy model.
It remains register-only and passive: it reads no guest payload, changes no
guest state or control flow, and does not execute native culling or LOD.

The batched AppData-backed Release capture `20260829T233419Z-p43632` completed
normally and reconciled 1,472,349 active title records. The ordered oracle
observed 2,424,492 candidate-threshold comparisons; all passed. The local
squared-distance gate admitted 208,775 of those candidates. Every admitted
candidate passed the spatial helper, after which the six-vector helper returned
0 for 163,907 observations, 1 for 8,620, and 2 for 36,248. Selected records
included 44,868 nonzero helper results, which makes the classifier's 0/1/2
domain materially useful for shadow-policy modeling rather than merely
structurally reachable.

All in-record ordering faults, invalid gate values, and invalid classifier
results were zero. ReXGlue resumed 1,736 comparison continuations and 149 helper
continuations outside an active entry scope; these were counted and excluded as
specified above. The authoritative census had zero lifecycle, identity,
overflow, or shutdown-open faults. Median performance was 30.224 FPS over 6,413
frames, there were no present-deadline misses, no fatal log signatures, and
Xenos remained the sole rendering authority.

## Title-result shadow selection

The first executable shadow policy turns the proved helper-result domain into a
per-record native decision without changing the title's decision. Within an
active title record, the model predicts selection when at least one six-vector
helper call returns 1 or 2; a modelled record with only zero results predicts
rejection. Records that never reach the helper remain explicitly unmodelled
rather than being guessed as invisible.

At record completion the shadow result is compared with the authoritative title
selection byte. Bounded category/outcome telemetry records model coverage,
predicted selections and rejections, exact title matches, false positives,
false negatives, records that observed each nonzero helper result, and records
that observed both. Qualification requires complete reconciliation with the
visibility census and zero false positives or false negatives.

This is an observational native state-machine model, not an independent camera
or frustum implementation. It reads only the already captured register result
domain, changes no guest state or control flow, performs no native draw, and
cannot suppress Xenos work. Its purpose is to prove the selection mapping before
the next batch mirrors the spatial helper inputs independently.

## Independent spatial-helper shadow

The second model mirrors `0x8243F9A0` independently at its exact callsite. A
pre-call hook at `0x82E2034C` reads only the helper's bounded arguments: six
query floats at offsets 0, 4, 8, 16, 20, and 24 plus two three-float segment
endpoints. The 52-byte payload contract is static, aligned, and record-scoped.

The host mirror preserves the title's two-stage scalar policy. A negative query
scalar at offset 20 accepts immediately. Otherwise it constructs the segment
midpoint with the title's 0.5 factor, computes the squared half-segment and
query distances, and accepts when query scalar 16 times the query distance is
less than or equal to query scalar 24 times the squared half-segment. Every
finite host prediction is compared with the low-byte title result at
`0x82E20350`.

Category/outcome telemetry reconciles one input and comparison with every
in-scope oracle helper observation. Invalid inputs, missing input/result pairs,
false positives, and false negatives fail closed. Unscoped continuation resumes
are counted and excluded. The mirror writes no guest memory, changes no control
flow, and still cannot cull, select LOD, draw, or suppress Xenos. Its runtime
qualification is batched with the title-result shadow model in one Release and
AppData session.

## Consolidated shadow-model qualification

Release/AppData session `20260830T000441Z-p37468` completed normally with no
fatal signatures and kept Xenos as the sole rendering authority. The
authoritative census reconciled 1,631,224 records with zero lifecycle, identity,
overflow, or shutdown-open faults. The title-result model matched all 28,092
modelled records with zero false positives or false negatives. The independent
spatial mirror matched all 232,692 in-scope helper results with zero invalid
inputs, missing pairs, false positives, or false negatives.

The optimized telemetry derives empty-record totals from the authoritative
census and performs no atomic updates for records that never reach either shadow
model. Median performance recovered to 30.153 FPS over 8,234 frames, with a
19.225 FPS one-percent low and zero present-deadline misses. This qualifies the
independent spatial helper and the title-result selection mapping for the next
category-classifier shadow milestone; native policy execution remains disabled.

## Independent category-classifier shadow

The third executable model mirrors the six-vector helper at `0x82441048`. A
pre-call hook at `0x82E20364` receives the two endpoint vectors from `v1` and
`v2` and bounded-reads the six 16-byte plane vectors at offsets 0 through 80.
The generated helper's `{+1,+1,-1,0}` vector constant transforms each plane's
three spatial axes before support selection and dot products. The transformed
sign of each axis selects the positive and negative support points. A
positive-support dot product greater than or equal to zero sets the intersection
bit; a negative-support dot product greater than zero sets the outside bits. The
combined bits map to the title's proved 0/1/2 result domain.

Every finite prediction is compared at `0x82E20368`. Category/outcome telemetry
reconciles one input and comparison with every in-scope oracle classifier call,
and fails closed on invalid inputs, missing pairs, or any result mismatch. The
payload contract is limited to 96 guest bytes per call. The model writes no guest
memory, changes no control flow, cannot cull or draw, and cannot suppress Xenos.
Release/AppData qualification was held until this complete checkpoint passed
its static, report, and compile gates. Consolidated Release/AppData
session `20260830T005146Z-p2496` then matched all 212,464 in-scope category
classifier calls, all 212,464 spatial-helper calls, and all 25,650 modelled
title results, with zero invalid inputs, missing pairs, or mismatches. The
process exited normally with no fatal signatures. Median performance was 30.570
FPS over 4,963 frames, with a 15.451 FPS one-percent low and zero
present-deadline misses. This qualifies the independent category classifier for
native visibility-policy assembly while native policy execution remains
disabled and Xenos remains authoritative.

## Independent policy-assembly shadow

The fourth model assembles the two independent mirrors into one record-level
decision. A native spatial prediction admits a candidate to the native category
classifier; category results 1 or 2 select the record, while records with only
result 0 are rejected. The title helper returns are no longer inputs to this
decision. Only the title's final record result is retained as the oracle used to
score the assembled native prediction.

Each candidate reads at most the already-qualified 52-byte spatial payload and
96-byte category payload. Category/outcome telemetry independently reconciles
spatial inputs and passes, category inputs and predicted result distribution,
model coverage, and final false-positive and false-negative counts against the
three prior qualified datasets. Any missing pair, invalid input, accounting
drift, or title-result mismatch fails qualification closed.

This remains a shadow checkpoint. It changes no guest state or control flow,
does not enable native culling or LOD, performs no native draw, and cannot
suppress Xenos.

The batched Release/AppData session `20260830T011157Z-p1896` reconciled
1,572,434 title records. Both independent mirrors matched all 223,473 in-scope
spatial and category calls, and the assembled model matched all 26,979 modelled
record outcomes with zero false positives, false negatives, invalid inputs, or
accounting faults. The process exited normally with no fatal signatures. Median
performance was 30.318 FPS over 8,063 frames, with a 19.396 FPS one-percent low
and zero present-deadline misses. This qualifies the independent assembly for
conservative native policy-execution design while execution and suppression
remain disabled and Xenos stays authoritative.

## Bounded native visibility workset

The first policy-execution boundary materializes every valid independent
record decision into a fixed 4,096-entry host workset keyed by receiver
address, receiver generation, and record index. Only the qualified spatial and
category inputs feed the decision. The title result remains a comparison
oracle and is never used to select the workset outcome.

The semantic-instance extraction hook is an upstream superset boundary. It
joins each observed record back to the latest workset entry using the same
exact identity. A selected join admits the record to the native
semantic-candidate stream. Rejected joins and missing joins are deliberately
excluded from that stream and retain Xenos replay; they describe records that
reach the broad helper boundary without an independently selected workset
decision, rather than native admission failures.

This is a real host-side policy handoff, but not title-side culling. It writes
no guest state, changes no title control flow, chooses no native LOD, uploads no
resource, issues no native draw, and cannot suppress Xenos. The workset,
assembly shadow, and semantic-instance summaries must reconcile in one runtime
session with zero overflow, invalid records, or title mismatches, and at least
one exact selected join, before a native drawing consumer may rely on the
filtered candidate stream. Rejected and missing observations remain accounted
fail-closed exclusions and can never enter that stream.

Release/AppData session `20260830T012818Z-p42316` proved that the semantic
helper is a superset boundary rather than a post-cull draw boundary. The
workset materialized 20,013 independently modelled decisions (8,920 selected
and 11,093 rejected) across 11 exact identities, with zero overflow, invalid
records, or title mismatches. Of 398,460 semantic-instance observations,
9,983 exact selected joins entered the candidate stream; 33,610 exact rejected
joins and 354,867 observations without a workset identity were excluded and
left on Xenos replay. All visibility reports reconciled, the process exited
normally with a clean fatal scan, and median performance was 30.241 FPS over
8,762 frames with a 19.518 FPS one-percent low and zero present-deadline
misses.
