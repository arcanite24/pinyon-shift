# Static-world unified presentation type census

Status: complete static RTTI census; concrete asset metadata remains the next
semantic boundary

## Purpose

The exact `CModelPresentation` owner raised a specific question: do separate
building or prop subclasses provide the missing semantic label? A complete
retail-image RTTI hierarchy census answers that question before adding more
runtime hooks.

`tools/discover-native-renderer-static-world-presentation-types.py` enumerates
every complete-object locator whose hierarchy contains
`Presentation_Unified::CModelPresentation`, resolves each associated vtable,
and locks the exact retail result.

## Exact result

Only two RTTI types exist in this hierarchy:

- `Presentation_Unified::CModelPresentation`; and
- `TRefCountedObjectThreadSafe<Presentation_Unified::CModelPresentation>`.

Each has one 18-slot primary surface whose slot 12 inherits exact draw method
`823F8DB8`, plus one one-slot secondary reference-count surface at object
offset 8. There is no building-, prop-, scenery-, or object-specific derived
presentation type in the retail image.

This is useful negative evidence. Searching for another semantic subclass
cannot produce the required classification. Individual identity must instead
come from the exact presentation/resource address, while a human-meaningful
building or prop label must come from bounded resource/asset metadata.

## Generate the report

```powershell
python tools/discover-native-renderer-static-world-presentation-types.py `
  .local/generated/default `
  --image .local/analysis/default-image.bin `
  --output .local/qualification/native-renderer-static-world-presentation-types.json
```

## Safety boundary

The census reads only retail RTTI, vtables, and generated AOT function
addresses. It exports no game payload, enables no runtime hook, makes no native
admission decision, and authorizes no suppression. Xenos remains authoritative.
