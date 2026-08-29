# Title-authoritative visibility and LOD contract

NR-05D begins with a passive boundary around the title's existing procedural
model visibility routine at `0x82E1FD00`. This checkpoint does not attempt to
name camera fields or reproduce the policy from partial ABI evidence. Instead,
it records the exact decisions that the title already commits to its runtime
records, preserving them as the reference contract for later native culling
and LOD work.

## Proven record loop

The reviewed slot-14 routine iterates descriptor and runtime records in lockstep:

- `r20` is the live `proceduralGeometry::CProceduralModels` receiver;
- `r16` is the record index;
- `r15` is the title's category partition;
- `r23` is `descriptor_base + record_index * 92`;
- `r21` is `runtime_base + record_index * 68`.

The static discovery contract validates the instructions surrounding four
observation boundaries:

| Boundary | Address | Meaning |
| --- | --- | --- |
| record entry | `0x82E20094` | descriptor/runtime identity is complete |
| LOD writes | `0x82E205E4`, `0x82E206DC` | title writes the selected index to runtime offset 104 |
| selection result | `0x82E206F8` | title has loaded the runtime selection byte at offset 18 |
| record completion | `0x82E2084C` | record result is final, before index/stride advance |

Reaching completion without reaching the result boundary is an early title
rejection. At the result boundary, the title's own comparison treats any
nonzero selection byte as accepted and zero as rejected. The census retains a
256-bin byte-value histogram instead of narrowing that bitfield to a boolean.
Category 9 is the path that commits a title-selected LOD index.

## Runtime census

The census maintains one thread-local active record and lock-free bounded
aggregates. It reports:

- total entries, completions, evaluated results, selections, evaluated
  rejections, and early rejections;
- per-category versions of the same accounting;
- LOD-bearing records, repeated title rewrites within those records, and a
  bounded 32-bin first-selected-index histogram;
- the complete 256-value title selection-byte histogram;
- receiver-generation joins, record identity mismatches, hook stack faults,
  category/LOD overflow, and records left open at shutdown.

The title can legitimately revisit either LOD store more than once for one
record. Those observations are reported as `lod_rewrites`; they are evidence
about the title's iterative policy, not lifecycle faults. Qualification fails
closed if record accounting is unbalanced, any identity or lifecycle join is
uncertain, a histogram overflows, no selected records or LOD-bearing records
are observed, or a selected category-9 record lacks its title LOD write.

Generate the static inventory and runtime report with:

```powershell
python tools/discover-native-renderer-dispatch.py `
  .local/generated/default `
  --image .local/generated/default/default.xex `
  --output .local/qualification/native-renderer-visibility-static.json

python tools/summarize-native-renderer-visibility.py `
  <diagnostic-jsonl> `
  --static .local/qualification/native-renderer-visibility-static.json `
  --output .local/qualification/native-renderer-visibility.json
```

## Qualification checkpoint

The AppData-backed open-world capture `20260829T223924Z-p43824` completed with
1,157,645 balanced record entries/completions and no identity, receiver,
overflow, orphan, or shutdown-open faults. It observed 8,968 title selections,
40,144 evaluated rejections, 1,108,533 early rejections, 4,484 LOD-bearing
category-9 records, and 14,553 legitimate in-record LOD rewrites. Selected LOD
indices were evenly split between 0 and 1 (2,242 records each).

The same 226.49-second capture retained a 30.355 FPS median, 29.745 Hz
simulation cadence, 59.375 Hz presentation cadence, zero presentation deadline
misses, and a normal process exit. The first capture encoded repeated LOD
writes under the old `duplicate_lod` diagnostic name; the v1 reporter records
that explicit compatibility normalization while the runtime now emits the
correct `lod_rewrites` name.

## Safety boundary

All hooks are observational. They read only registers already holding title
decisions; they do not read payload memory, write guest state, alter control
flow, upload native resources, submit native draws, reorder work, or suppress
Xenos work. Native culling and native LOD remain disabled. Xenos remains the
sole rendering and visibility authority until a later policy model is proven
against this census and independently passes the plan's admission gates.
