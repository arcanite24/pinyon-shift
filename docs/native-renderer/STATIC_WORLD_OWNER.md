# Static-world model-presentation ownership

Status: exact presentation-to-renderer ownership and transform dispatch proved;
passive runtime join implemented; qualification pending the next batched C1/C2
run

## Purpose

The generic `CSimpleModelResource` member graph identifies the model, submodel,
and mesh that emitted a draw, but it does not identify the title object that
owns the renderer. `tools/discover-native-renderer-static-world-owner.py`
closes that structural gap without assigning unproved building or prop
semantics.

## Exact owner path

Retail RTTI, vtables, and generated AOT instructions prove:

- `Presentation_Unified::CModelPresentation` uses primary vtable `822432D4`,
  while its proved thread-safe ref-counted complete object uses primary vtable
  `82002464`; both inherit slot 12 target `823F8DB8` at object offset zero;
- its slot 12 is method `823F8DB8`, with one balanced exit at `823F8FA0`;
- the owner stores its exact `CSimpleModelResource` reference at offset 148,
  state at offset 144, and renderer at offset 1608;
- slot 7 initializes the normal resource path by passing owner offset 148 to
  the already-proved `CSimpleModelResource` binder `82C48038`;
- helper `823F8980` reads the offset-148 reference, constructs the exact
  `CSimpleModelRenderer` through `82C4E3A0`, stores it at offset 1608, and
  invokes renderer bind slot 0; the binding and reference-assignment helpers
  copy that same resource address into renderer offset 72; and
- the same slot-12 scope later loads the offset-1608 renderer and invokes
  renderer slot 12, whose exact vtable target is `82C4CCC8`; and
- immediately before that draw, the scope loads the complete 64-byte transform
  from owner offset 80 and invokes renderer slot 6 at `82C4C568`, which copies
  the same 16 words to renderer offset 128.

This creates a safe synchronous join: an exact SimpleModel renderer dispatch
occurring inside the balanced presentation slot-12 scope carries the
`CModelPresentation` and exact `CSimpleModelResource` addresses into existing
packet and prepared-draw provenance. Runtime also requires the owner's
offset-1608 renderer field to equal the nested dispatch receiver. Calls on
other dynamic presentation types that share the implementation are counted as
excluded vtable mismatches, while exact-owner field mismatches fail closed.
The join changes no title behavior.

The passive observer reads the transform only inside the exact presentation
scope, exports its hash and 16 numeric words, and carries it through the exact
renderer, PM4 packet, and prepared-draw lineage. Independent read, renderer
join, and packet-origin accounting fails closed on missing provenance. No
matrix convention or building/prop category is inferred from static code.

The complete RTTI hierarchy census is documented in
[`STATIC_WORLD_PRESENTATION_TYPES.md`](STATIC_WORLD_PRESENTATION_TYPES.md). It
proves there is no more-specific building or prop presentation subclass.

## Generate the report

```powershell
python tools/discover-native-renderer-static-world-owner.py `
  .local/generated/default `
  --image .local/analysis/default-image.bin `
  --output .local/qualification/native-renderer-static-world-owner.json
```

## Remaining boundary

`CModelPresentation`, its renderer resource, and its complete transform are an
exact title-owned static-model instance identity, not proof that the asset
should be called a building rather than a prop. The bounded resource-key and
effect/texture reference path is now proved in
[`STATIC_WORLD_ASSET_METADATA.md`](STATIC_WORLD_ASSET_METADATA.md), but its
payload-free category join and representative streaming transitions remain
open. The title-authored offline spatial catalog and its deliberately unproved
runtime boundary are documented in
[`STATIC_WORLD_INSTANCE_CLASSIFICATION.md`](STATIC_WORLD_INSTANCE_CLASSIFICATION.md).
This checkpoint changes no guest data, native admission, publication, or
suppression; Xenos remains authoritative.

The combined runtime qualifier requires this report through `--owner`, the
bounded metadata report through `--asset-metadata`, and the mesh field proof
through `--mesh-semantics`; all remain static inputs to the batched runtime
gate.
