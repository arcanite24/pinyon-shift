# Static-world SimpleMesh semantics

Status: bounded geometry draw and material-binding fields proved and carried
to prepared-draw provenance; batched runtime qualification remains pending

## Purpose

The member graph proves which `CSimpleMesh` emits a draw. This checkpoint
identifies the exact fields and helper sequence used to turn that mesh into a
title indexed draw, without interpreting or exporting mesh payload bytes.

## Geometry contract

`tools/discover-native-renderer-static-world-mesh-semantics.py` proves:

- mesh offset 36 supplies the numeric primitive type;
- mesh offset 96 supplies the index-buffer binding installed through
  `8244D760` and cleared immediately after the draw;
- mesh offset 100 supplies the source element count;
- helper `82C48558` converts the element count into a primitive count for the
  supported numeric primitive modes; and
- the exact scale/bias table at `820023F0` converts that result into draw
  argument `r7` before indexed-draw emitter `82416380`.

The emitter receives the graphics context in `r3`, primitive type in `r4`,
zero base/index offsets in `r5`/`r6`, and the derived element count in `r7`.

## Material-binding boundary

The same path proves a bounded state/material branch:

- submodel offsets 112, 39, and 32 gate and supply state binding to
  `82410A70`; and
- mesh offset 128 holds an optional reference whose resource at offset 168 is
  resolved through virtual slot 5 and bound with `8244E728`; the alternate
  branch binds the renderer's existing `r22` source through the same helper.

This is enough to observe stable geometry/material binding families. Complete
vertex-fetch layouts, material parameter blocks, building/prop labels, and
native admission remain unproved.

## Runtime lineage

The passive runtime observer reads only the proved numeric fields after the
resource/model/submodel/mesh relation and RTTI vtables pass their existing
exact guards. It carries primitive type, index-buffer binding, source element
count, submodel state selection, and the optional material reference through
the physical PM4 origin into prepared-draw provenance. Independent observation,
read-fault, packet-origin, and missing-origin counters make the combined
qualifier fail closed. No vertex or material payload bytes are exported.

Runtime evidence remains deferred to the next combined C1/C2 AppData session.
Until that session qualifies the lineage, this checkpoint is implementation
complete but not runtime-qualified.

## Generate the report

```powershell
python tools/discover-native-renderer-static-world-mesh-semantics.py `
  .local/generated/default `
  --image .local/analysis/default-image.bin `
  --output .local/qualification/native-renderer-static-world-mesh-semantics.json
```

The proof is static and payload-free. It changes no guest state or title
control flow; Xenos remains authoritative.
