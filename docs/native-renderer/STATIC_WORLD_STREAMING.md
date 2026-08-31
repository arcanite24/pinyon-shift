# Static-world SimpleModel payload-reset transitions

Status: exact payload-reset boundaries and generation invalidation implemented;
runtime qualification pending

## Purpose

An allocation generation is not sufficient for open-world streaming. A live
`CSimpleModelResource` can release and replace owned payload while retaining
the same object address. Prepared-draw provenance must become stale when that
happens, even if the renderer still points at the same resource object.

`tools/discover-native-renderer-static-world-streaming.py` proves the minimum
exact reset surface against the retail image and generated AOT instructions.
It names only structural behavior visible in those instructions; it does not
claim that these two methods cover every title streaming route.

## Exact transitions

The resource's vtable and instruction flow prove:

- slot 15, `82C46410`, refreshes the offset-112 graph using the offset-76
  binding object through `82C462D0`;
- slot 16, `82C46440`, reads the owned pointer at offset 64, clears it before
  invoking release slot 3, then checks the offset-112 graph. Balanced hooks
  are `82C46440` and `82C46480`;
- slot 22, shared method `82C222C8`, invokes virtual slot 15, preserves its
  result, then clears and releases the same offset-64 pointer. Balanced hooks
  are `82C222C8` and `82C2231C`; exact RTTI excludes other resource classes.

Every completed exact transition must leave offset 64 null. The passive
registry then increments a payload generation independently from the resource
allocation generation. Renderer binding snapshots both generations, and an
exact draw scope, PM4 packet, or prepared-draw join fails closed when either
one is stale. The hook never changes guest data, title control flow, native
admission, or Xenos authority.

## Generate the static report

```powershell
python tools/discover-native-renderer-static-world-streaming.py `
  .local/generated/default `
  --image .local/analysis/default-image.bin `
  --output .local/qualification/native-renderer-static-world-streaming.json
```

The combined runtime qualifier now requires the streaming report:

```powershell
python tools/summarize-native-renderer-static-world-runtime-join.py `
  .local/preview/logs/<session>.jsonl `
  --static .local/qualification/native-renderer-static-world-ingress.json `
  --lifetime .local/qualification/native-renderer-static-world-lifetime.json `
  --resource .local/qualification/native-renderer-static-world-resource.json `
  --streaming .local/qualification/native-renderer-static-world-streaming.json `
  --graph .local/qualification/native-renderer-static-world-graph.json `
  --owner .local/qualification/native-renderer-static-world-owner.json `
  --asset-metadata .local/qualification/native-renderer-static-world-asset-metadata.json `
  --session <session> `
  --output .local/qualification/native-renderer-static-world-runtime-join.json
```

The report requires a balanced exact payload reset and verifies that every
completion advances the payload generation. Non-SimpleModel calls through the
shared slot-22 implementation are counted as exclusions, not faults.

## Remaining boundary

Runtime evidence must show which transition paths occur during representative
driving and streaming, whether every later draw is rebound to the new payload
generation, and whether other independent invalidation routes exist. Concrete
building/prop identity and mesh/material ownership also remain open. Therefore
this checkpoint enables no native upload, draw, publication, or suppression;
Xenos remains authoritative.

The adjacent member-lineage proof is documented in
[`STATIC_WORLD_GRAPH.md`](STATIC_WORLD_GRAPH.md).
