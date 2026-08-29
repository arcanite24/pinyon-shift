# Semantic batch-equivalence ladder

This NR-05C checkpoint separates native instancing compatibility from broader
state reuse. It is a passive measurement layer: every draw still executes on
Xenos, and native upload, draw, batching, reordering, admission, and
suppression remain disabled.

## Why a second identity is required

The first exact-order census used the complete prepared-template and resource
identity. Session `20260829T211909Z-p31988` found 635,197 eligible draws but no
multi-draw run. That identity is useful as a fail-closed replay key, but it is
too specific for measuring native instancing.

The exact prepared-template hash intentionally retains the raw observed state
needed to audit replay. Some of that state is resource-bearing: vertex-buffer
sizes, draw ranges, texture fetch words containing base and mip addresses, and
EDRAM target bases. The equivalence ladder therefore adds a separate
`batch_pipeline_key`; it does not silently weaken the exact replay identity.

## Resource-free pipeline identity

The batch pipeline key retains:

- prepared host primitive, shader type, index mode, render-target formats,
  depth/color state, and prepared-stage completeness;
- vertex declaration, binding stride/endianness, and shader fetch mapping;
- texture instruction and sampler layout;
- shaders and specialization masks;
- opaque render state and shader constant usage layout.

It excludes and records separately:

- index and vertex-buffer addresses and byte sizes;
- index count and vertex range arguments;
- texture base and mip addresses;
- EDRAM color and depth target bases;
- shader-used constant values.

Texture fetch dwords 1 and 5 are normalized by masking their 20-bit base and
mip page fields. Color and depth target state masks the 12-bit EDRAM base while
retaining format state. The original raw hashes remain available for audit.

## Three consecutive equivalence levels

All levels preserve exact draw order and stop at frame boundaries or rejected
draws:

1. `mesh_material_instance` combines the resource-free pipeline, exact draw
   arguments, geometry resources, texture resources, and render target. A
   multi-draw run is the narrow candidate for explicit native instancing.
2. `material_state_reuse` combines pipeline, texture resources, and render
   target while allowing geometry and draw arguments to differ. It measures
   material/state binding reuse, not draw-count reduction.
3. `pipeline_state_reuse` uses only the resource-free pipeline key. It measures
   prepared-pipeline reuse and does not imply compatible resources or targets.

Each level records consecutive runs, multi-draw coverage, maximum run length,
semantic-instance switches, and shader-parameter switches. The parameter hash
contains only shader-used vertex/pixel float constants plus masked used
boolean and loop constants. A mesh/material run with instance and parameter
switches proves that a later executor needs an explicit per-instance parameter
buffer; it does not authorize one.

The runtime also records total and maximum compact parameter payload bytes.
The fail-closed observation limit is 2,756 bytes per draw: up to 64 indexed
float constants per shader stage, eight used boolean blocks, and 32 used loop
constants. Overflowed float-constant observations are rejected before they can
enter any equivalence level.

## Fail-closed report

`tools/summarize-native-renderer-semantic-batches.py` emits schema
`pinyon-shift.native-renderer-semantic-batch-admission.v3`. It requires one
complete summary for every equivalence level and reconciles every retained
entry to the exact eligible-draw total. Continuation accounting must match
both semantic-instance and parameter transitions, with zero table overflow.

`mesh_material_instancing_opportunity_proved` requires a multi-draw
mesh/material run, nonzero potential reduction, and at least one semantic
instance switch. `instancing_parameter_path_required` additionally requires a
shader-parameter switch. Neither result enables execution.

## Qualification result

Release/AppData session `20260829T214335Z-p7092` observed 1,180,157 prepared
draws over 3,562 frames. The fail-closed predicates admitted 798,633 draws and
rejected 381,524. The session loaded the installed AppData profile into live
gameplay, retained Xenos authority, found no overflow, and shut down normally.

The exact replay identity and `mesh_material_instance` identity both produced
only single-draw runs. Consequently, this scene does not justify a native
instancing executor or an instance-parameter upload path yet.

The broader reuse levels did find material opportunities:

- `material_state_reuse` found 76,302 multi-draw runs covering 169,902 draws,
  with maximum run length 5 and 93,600 reusable continuations (11.72%).
- `pipeline_state_reuse` found 144,898 multi-draw runs covering 512,218 draws,
  with maximum run length 36 and 367,320 reusable continuations (45.994%).

The largest compact shader-parameter payload was 700 bytes, below the
2,756-byte fail-closed bound. These results support pursuing state-binding and
prepared-pipeline caches as the next implementation batch, but those reuse
paths must not be reported as draw-count reduction. Native execution,
reordering, admission, upload, draw, and suppression remain disabled.

The follow-up bounded shadow-cache contract is documented in
`docs/native-renderer/SEMANTIC_STATE_CACHE.md`.
