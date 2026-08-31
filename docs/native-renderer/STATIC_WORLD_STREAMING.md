# Static-world SimpleModel payload-reset transitions

Status: complete class-exposed invalidation surface and generation tracking
proved; representative runtime qualification pending

## Purpose

An allocation generation is not sufficient for open-world streaming. A live
`CSimpleModelResource` can release and replace owned payload while retaining
the same object address. Prepared-draw provenance must become stale when that
happens, even if the renderer still points at the same resource object.

`tools/discover-native-renderer-static-world-streaming.py` proves the complete
23-slot class vtable and its exact reset surface against the retail image and
generated AOT instructions. It names only structural behavior visible in those
instructions; external callers and representative title streaming behavior
still require runtime qualification.

## Exact transitions

The resource's vtable and instruction flow prove:

- all 23 vtable slots resolve to the locked retail target census, covering 14
  unique functions;
- slot 0 destruction reaches `82C47DF8`, which calls base destructor
  `82E45B20`; the base destructor clears/releases the same offset-64 owned
  reference;
- slot 15, `82C46410`, refreshes the offset-112 graph using the offset-76
  binding object through `82C462D0`;
- slot 16, `82C46440`, reads the owned pointer at offset 64, clears it before
  invoking release slot 3, then checks the offset-112 graph. Balanced hooks
  are `82C46440` and `82C46480`;
- slot 22, shared method `82C222C8`, invokes virtual slot 15, preserves its
  result, then clears and releases the same offset-64 pointer. Balanced hooks
  are `82C222C8` and `82C2231C`; exact RTTI excludes other resource classes.

No other class-vtable target clears the live offset-64 payload. Slots 16 and 22
therefore cover every live-object payload reset exposed by this class, while
slot 0 covers destruction. The broader claim that representative gameplay
exercises every relevant streaming transition intentionally remains false.

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
  --mesh-semantics .local/qualification/native-renderer-static-world-mesh-semantics.json `
  --session <session> `
  --output .local/qualification/native-renderer-static-world-runtime-join.json
```

The report requires a balanced exact payload reset and verifies that every
completion advances the payload generation. Non-SimpleModel calls through the
shared slot-22 implementation are counted as exclusions, not faults.

## Remaining boundary

Runtime evidence must show which transition paths occur during representative
driving and streaming and whether every later draw is rebound to the new
payload generation. Any invalidation route outside the complete class vtable
must also be identified from that evidence. Concrete building/prop identity
and mesh/material ownership remain open. Therefore this checkpoint enables no
native upload, draw, publication, or suppression; Xenos remains authoritative.

The adjacent member-lineage proof is documented in
[`STATIC_WORLD_GRAPH.md`](STATIC_WORLD_GRAPH.md).
