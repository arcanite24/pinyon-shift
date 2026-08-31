# Static-world SimpleModel resource boundary

Status: exact resource type, factory registration, and lifetime proved; runtime
qualification pending

## Purpose

The renderer's offset-72 graph cannot safely identify static-world work while
it is only an opaque pointer. Phase C2 needs proof that the bound object is an
exact `CSimpleModelResource`, that both factory reuse and allocation paths
cross one registration boundary, and that allocation reuse cannot join an old
prepared draw to a new resource generation.

`tools/discover-native-renderer-static-world-resource.py` validates those
facts against the payload-free retail image and generated AOT instruction
flow. The report contains addresses and structural facts only.

## Exact factory and binding path

- Renderer bind helper `82C48038` passes `renderer + 72` as the output of
  factory callback `82C47F10`.
- The allocation path reserves 320 bytes, invokes constructor `82C47DA0`, and
  installs exact `CSimpleModelResource` vtable `82229294`.
- Hook `82C47FBC` publishes the generation after that final vtable store and
  before reference assignment helper `824E81A8` publishes the pointer.
- Existing and newly allocated resources converge at `82C4802C`, after the
  factory's registration/list insertion. The hook observes the final output
  pointer without changing title state or control flow.
- Vtable slot zero is deleting destructor `82C47EC0`. Complete destructor
  `82C47DF8` and exit hook `82C47E44` bound the exact resource lifetime.

The runtime registry assigns an independent generation to every published
resource address. Registration, renderer binding, exact renderer scope, PM4
packet provenance, and prepared-draw provenance must agree on the same live
generation. Null, unregistered, wrong-vtable, destroying, destroyed, stale,
unmapped, or overflowing entries fail closed and remain Xenos-owned.

## Generate the static report

```powershell
python tools/discover-native-renderer-static-world-resource.py `
  .local/generated/default `
  --image .local/analysis/default-image.bin `
  --output .local/qualification/native-renderer-static-world-resource.json
```

The batched runtime qualifier requires all five static reports:

```powershell
python tools/summarize-native-renderer-static-world-runtime-join.py `
  .local/preview/logs/<session>.jsonl `
  --static .local/qualification/native-renderer-static-world-ingress.json `
  --lifetime .local/qualification/native-renderer-static-world-lifetime.json `
  --resource .local/qualification/native-renderer-static-world-resource.json `
  --streaming .local/qualification/native-renderer-static-world-streaming.json `
  --graph .local/qualification/native-renderer-static-world-graph.json `
  --owner .local/qualification/native-renderer-static-world-owner.json `
  --session <session> `
  --output .local/qualification/native-renderer-static-world-runtime-join.json
```

`--allow-checkpoint` remains diagnostic only. A periodic checkpoint cannot
prove clean shutdown and never enables native admission.

## Remaining boundary

This proves the exact dynamic type and generation of the resource bound to a
live renderer, plus the factory registration boundary and resource destructor.
It does not identify a concrete building or prop, decode mesh/material
members, or prove every independent streaming invalidation route. The first
two exact payload-reset transitions and their independent generation boundary
are documented in
[`STATIC_WORLD_STREAMING.md`](STATIC_WORLD_STREAMING.md). Native upload, draw,
publication, and suppression remain disabled; Xenos stays authoritative.
