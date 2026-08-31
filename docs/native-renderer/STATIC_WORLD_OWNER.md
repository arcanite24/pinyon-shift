# Static-world model-presentation ownership

Status: exact presentation-to-renderer ownership and passive runtime join
implemented; runtime qualification pending the next batched C1/C2 run

## Purpose

The generic `CSimpleModelResource` member graph identifies the model, submodel,
and mesh that emitted a draw, but it does not identify the title object that
owns the renderer. `tools/discover-native-renderer-static-world-owner.py`
closes that structural gap without assigning unproved building or prop
semantics.

## Exact owner path

Retail RTTI, vtables, and generated AOT instructions prove:

- `Presentation_Unified::CModelPresentation` uses primary vtable `822432D4`;
- its slot 12 is method `823F8DB8`, with one balanced exit at `823F8FA0`;
- the owner stores its resource reference at offset 148, state at offset 144,
  and renderer at offset 1608;
- helper `823F8980` reads the offset-148 reference, constructs the exact
  `CSimpleModelRenderer` through `82C4E3A0`, stores it at offset 1608, and
  invokes renderer bind slot 0; and
- the same slot-12 scope later loads the offset-1608 renderer and invokes
  renderer slot 12, whose exact vtable target is `82C4CCC8`.

This creates a safe synchronous join: an exact SimpleModel renderer dispatch
occurring inside the balanced presentation slot-12 scope carries the
`CModelPresentation` and opaque presentation-resource addresses into existing
packet and prepared-draw provenance. Runtime also requires the owner's
offset-1608 renderer field to equal the nested dispatch receiver. Calls on
other dynamic presentation types that share the implementation are counted as
excluded vtable mismatches, while exact-owner field mismatches fail closed.
The join changes no title behavior.

## Generate the report

```powershell
python tools/discover-native-renderer-static-world-owner.py `
  .local/generated/default `
  --image .local/analysis/default-image.bin `
  --output .local/qualification/native-renderer-static-world-owner.json
```

## Remaining boundary

`CModelPresentation` is an exact title-owned presentation class, not proof that
an individual instance is a building rather than a prop. Mesh/material field
semantics and representative streaming transitions also remain open. This
checkpoint changes no guest data, native admission, publication, or
suppression; Xenos remains authoritative.

The combined runtime qualifier now also requires this static report through
`--owner .local/qualification/native-renderer-static-world-owner.json`.
