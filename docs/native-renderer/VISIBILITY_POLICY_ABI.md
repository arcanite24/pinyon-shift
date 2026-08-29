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

## Deliberately unproven semantics

The arithmetic is consistent with point-to-box squared distance and the helper
pair is consistent with spatial/frustum policy, but those names are not yet an
ABI contract. We have not proved:

- which shared-context vector is minimum, maximum, eye, or focus position;
- a camera or frustum-plane layout;
- whether the category scalars are extents, margins, ranges, or mode data;
- the descriptor/runtime scalar units or all category-specific branches.

Accordingly this checkpoint enables only a future passive input/outcome
correlation census. Native policy execution, native culling, native LOD, guest
state mutation, draw suppression, and Xenos replacement remain disabled.
