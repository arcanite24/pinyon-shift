# Vehicle asset/material binding

Status: exact static title-owned tire/wheel discriminator proved; passive
runtime census implemented and awaiting the next batched gameplay run.

## Exact edge

Retail function `82543558` constructs the car-specific tire/wheel shader
settings path. It selects the shared Normal or SLOD tire settings, appends the
title's `game:\media\Wheels\` root, the model-owned MSVC string at offset
1712, and the `ShaderSettings` suffix. Function `82549670` binds that result to
the destination object and optionally loads its UI settings.

The car-resource constructor `824D11B0` calls this binding function twice. At
both sites, `r3` is the car material root and `r4` is exactly root plus 1056.
The retail image independently identifies the related
`CCarMaterialSettingsResourceType`, `CCarModelResourceType`,
`CCarMaterialSettingsResource`, and `CCarModelResource` RTTI/vtable surfaces.
`discover-native-renderer-vehicle-asset-material.py` locks all of these
relationships and fails if any instruction, string, type, locator, vtable, or
call count drifts.

## Passive runtime join

The census hook at `82549670` records only:

- the root and exact root-plus-1056 binding addresses;
- a length and hash of the model-owned asset key at root plus 1712;
- the UI-load and Normal/SLOD flags; and
- exact backend signatures if either retained address later appears directly
  in title draw provenance.

The bounded table has 128 binding rows and 16 backend signatures per row.
Every observation is accounted as a valid exact relation, an invalid owner
relation, or an asset-key read fault. No path text or asset bytes are logged.

## What this proves

This is the independent title-owned discriminator required by the resource
contribution work, but only for the tire/wheel shader-settings family. It does
not yet assign one of the 15 geometry resources to body paint, glass, wheels,
lights, livery, or exceptional work. That requires the next batched run to
join a binding/backend signature with an isolated visual contribution (or to
show that a narrower downstream bind edge is still needed).

Xenos remains authoritative. The hook cannot alter guest state, publish a
native draw, admit a resource, or enable suppression.

## Runtime decision

`summarize-native-renderer-vehicle-material-bindings.py` consumes the final
JSONL census and the qualified 15-resource contribution report. It validates
strict hook accounting and safety, then maps exact backend draw signatures to
each contribution's two prepared variants.

The result is intentionally three-way:

- `qualified` only when every observed binding signature maps to one unique
  geometry resource;
- `bounded_negative_result/no_direct_binding_to_draw_join` when neither
  retained address reaches draw provenance; or
- `bounded_negative_result/binding_to_geometry_join_not_unique` when the edge
  is real but does not isolate one contribution.

Even a unique join remains a tire/wheel candidate until its isolated visual
capture agrees. The qualifier cannot promote, publish, or suppress it.

## Reproduction

```powershell
python tools/discover-native-renderer-vehicle-asset-material.py `
  .local/generated/default `
  --image C:\path\to\default-image.bin `
  --output .local/qualification/native-renderer-vehicle-asset-material.json

python tools/summarize-native-renderer-vehicle-material-bindings.py `
  .local/logs/pinyon_shift.jsonl `
  --contributions `
    .local/qualification/native-renderer-vehicle-resource-contributions-v1.json `
  --output `
    .local/qualification/native-renderer-vehicle-material-bindings.json
```
