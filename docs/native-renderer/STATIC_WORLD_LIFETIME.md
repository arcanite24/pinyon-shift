# Static-world SimpleModel renderer lifetime

Status: static lifetime and owned-graph boundary proved; runtime qualification
pending

## Purpose

The generic `CSimpleModelRenderer` draw ingress is useful only if its object
and graph identities cannot be confused across allocation reuse, rebinding, or
destruction. Phase C2 therefore needs a generation boundary around the exact
renderer lifetime and its owned offset-72 graph field before runtime evidence
may classify its prepared draws.

`tools/discover-native-renderer-static-world-lifetime.py` validates that
boundary against the payload-free retail image and generated AOT instruction
flow. It exports addresses and structural facts only.

## Exact lifetime

- `82C4E3A0` allocates 368 bytes and invokes complete constructor `82C4DF78`.
- The constructor installs vtable `82001B64`, initializes offset 72 to null,
  and reaches the post-construction publication hook at `82C4E094`.
- Vtable slot 16 is deleting destructor `82C4E420`. It invokes complete
  destructor `82C4E1F8`, whose balanced runtime hooks are `82C4E1F8` and
  `82C4E264`, then conditionally frees the allocation.
- Destructor cleanup `82C4E0A0` clears the offset-72 graph field and invokes
  release slot 3 on the previous graph.

The earlier ingress report intentionally proves vtable extents but does not
assign lifecycle semantics to slot zero. Its field is now named
`slot_zero_target`; the exact analysis above proves the renderer's deleting
destructor at slot 16.

## Exact graph ownership

- Vtable slot 1 (`82C4CC50`) passes `renderer + 72` to binding helper
  `82C48038`; the completion hook is `82C4CCB0`.
- Vtable slot 15 (`82C4C6A8`) reads and clears offset 72, then tail-dispatches
  release slot 3 on the previous graph.
- Destructor cleanup `82C4E0A0` performs the same clear-before-release
  ownership transition.
- Vtable slot 12 (`82C4CCC8`) reads that exact field before emitting any
  indexed draw.

The runtime registry publishes a new renderer generation only after completed
construction. Graph binds receive a separate generation, and prepared-draw
provenance carries both generations. Unregistered, destroying, destroyed,
unbound, or mismatched objects fail closed before packet attribution. All
title allocation, release, draw, and control-flow behavior remains unchanged.

## Generate the static report

```powershell
python tools/discover-native-renderer-static-world-lifetime.py `
  .local/generated/default `
  --image .local/analysis/default-image.bin `
  --output .local/qualification/native-renderer-static-world-lifetime.json
```

The runtime join now requires the ingress, renderer-lifetime, exact-resource,
payload-reset, and member-graph reports:

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

## Remaining boundary

This proves a live renderer generation and the graph it owns at draw time.
The graph's exact dynamic type, factory registration, and resource generation
are proved separately in
[`STATIC_WORLD_RESOURCE.md`](STATIC_WORLD_RESOURCE.md). Concrete building or
prop instances, mesh/material members, and every streaming invalidation route
remain pending. Native admission, publication, and suppression remain
disabled; Xenos stays authoritative.
