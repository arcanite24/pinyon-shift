# Semantic state-cache admission

This NR-05C checkpoint turns the measured material and pipeline reuse into a
bounded cache contract. It is still a shadow implementation: it records the
work a future native renderer could avoid, but does not create native state
objects, bind native resources, issue native draws, reorder work, or suppress
Xenos output.

## Cache identities

The cache consumes the resource-free pipeline identity established by the
semantic batch-equivalence ladder:

- `pipeline_state` keys the immutable prepared pipeline, shader and
  specialization state, resource-free vertex/texture layouts, and normalized
  render state;
- `material_state` adds texture-resource and render-target-resource identities
  to the pipeline key.

Geometry resources, draw arguments, and shader-parameter values are not part
of either cached state object. They remain per-draw inputs. Texture and target
content invalidation is deliberately outside this descriptor/state cache and
continues to require the resource-generation and deferred-destruction work in
NR-04D and PR 9.

## Bounded replacement policy

Each level is measured simultaneously at three four-way set-associative
profiles: compact (64 entries), balanced (256), and headroom (1,024). Lookups
inspect only four entries in each profile. A miss fills an empty way or evicts
the least-recently-used way in that bucket, giving deterministic bounded
memory and constant lookup cost without heap allocation. Measuring all three
profiles in one gameplay session avoids a separate build and run merely to
select capacity.

The cache lifetime is one census session. Reset and uninstall discard all
shadow entries; no native object survives the session boundary.

## Reuse classes

Every fail-closed eligible semantic draw performs one lookup in both cache
levels. Hits are partitioned exactly once into:

- `consecutive_hits`: the immediately preceding eligible draw in the same
  frame used the same key, so a later executor could elide a redundant bind;
- `nonconsecutive_same_frame_hits`: the object was already resident in this
  frame, but another state intervened, so construction is avoided while a bind
  remains required;
- `cross_frame_hits`: the resident object was last used in an earlier frame.

A rejected draw breaks bind continuity because it may change authoritative
guest state. Frame boundaries also prevent bind elision. Cache residency may
continue across both boundaries because object identity remains explicit.

Misses model object construction. Hits model construction avoided. Only
consecutive hits count as binding elisions; all other lookups count as required
bindings. This prevents the broader cache-hit metric from being mislabeled as
command reduction.

## Fail-closed report

`tools/summarize-native-renderer-semantic-batches.py` emits schema
`pinyon-shift.native-renderer-semantic-batch-admission.v3`. It requires one
complete summary for every cache level and capacity profile and verifies:

- one lookup per eligible draw at both levels;
- hits plus misses equal lookups;
- the three hit classes partition all hits;
- construction and binding accounting reconcile;
- resident and maximum-resident counts stay within capacity;
- eviction, bucket, way, capacity, policy, and percentage fields agree; and
- native objects, bindings, draws, reordering, and suppression all remain off
  while Xenos stays authoritative.

The report exposes `state_object_cache_reuse_proved` and
`state_binding_elision_proved` as evidence flags. Neither flag admits native
execution. It also selects the smallest zero-eviction profile independently
for material and pipeline state when the capture proves one.

## Qualification result

Release/AppData session `20260829T220629Z-p41464` observed 699,166 prepared
draws over 2,116 frames and admitted 473,474. All six cache summaries
reconciled one lookup per eligible draw. The installed profile loaded into
live festival gameplay, Xenos remained authoritative, no native state object
or binding was created, no suppression gate changed, and shutdown was clean.

Material-state results were:

- compact: 473,038 hits, 436 misses, 99.908% hit rate, and 388 evictions;
- balanced: 473,406 hits, 68 misses, 99.986% hit rate, and one eviction;
- headroom: 473,406 hits, 68 misses, 99.986% hit rate, zero evictions, and 68
  resident entries.

All material profiles found 55,368 consecutive binding elisions (11.694%).
The zero-eviction selection is therefore `headroom`; the balanced profile is
nearly sufficient but does not meet the strict gate in this capture.

Pipeline-state results were identical at every capacity: 473,440 hits, 34
misses, 99.993% hit rate, zero evictions, and 34 resident entries. They found
217,928 consecutive binding elisions (46.027%). The smallest zero-eviction
selection is `compact`.

The 1,024-entry material cache also measured 384,003 non-consecutive
same-frame hits and 34,035 cross-frame hits. The 64-entry pipeline cache
measured 234,310 and 21,202 respectively. These prove that an object cache is
valuable independently of consecutive bind elision.

The session measured 30.082 median FPS, 15.109 FPS one-percent low, 59.019 Hz
presentation, and zero present-deadline misses. No fatal, panic, assertion,
device-loss, unhandled-exception, or access-violation signature appeared. The
state-cache report SHA-256 is
`46C1C045A52FAF32F06AFE56AA82F5B6FF87495DA83DA6D2069F5F55E7805D9D`.

The next implementation may use the selected capacities for native immutable
state objects, but resource lifetime and fence-gated destruction must be in
place before any cached native resource view can outlive its observed guest
generation. Native execution and suppression remain inadmissible.
