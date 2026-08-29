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
