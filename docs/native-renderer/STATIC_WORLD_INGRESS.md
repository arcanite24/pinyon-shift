# Static-world SimpleModel ingress

Status: static title proof; runtime identity join pending

## Purpose

Phase C2 needs an exact title-owned boundary for buildings and props before
native work can be admitted. Broad shader, draw-frequency, and texture
similarity are not sufficient. The retail RTTI graph exposes a narrower lead:
the generic `CSimpleMesh`, `CSimpleSubModel`, `CSimpleModel`, streamed
`CSimpleModelResource`, renderer, deferred renderer, and unified model
presentation surfaces.

`tools/discover-native-renderer-static-world-ingress.py` validates those
surfaces directly against the payload-free retail image and generated AOT
function inventory. It does not inspect game assets or runtime payloads.

## Exact surfaces

| Class | Surface | Locator | Vtable | Slots |
|---|---|---:|---:|---:|
| `CSimpleMesh` | primary | `823521C4` | `822291A0` | 6 |
| `CSimpleSubModel` | primary | `82352214` | `822291BC` | 7 |
| `CSimpleModel` | secondary | `823522C0` | `822291E8` | 7 |
| `CSimpleModel` | primary | `82352268` | `82229208` | 9 |
| `CSimpleModelResource` | primary | `82352328` | `82229294` | 23 |
| `CSimpleModelRenderer` | primary | `8235275C` | `82001B64` | 17 |
| `CSimpleModelRendererDeferred` | secondary | `822EF198` | `82021328` | 1 |
| `CSimpleModelRendererDeferred` | primary | `822EF148` | `82021334` | 16 |
| `Presentation_Unified::CModelPresentation` | secondary | `82363464` | `822432C8` | 1 |
| `Presentation_Unified::CModelPresentation` | primary | `823633E8` | `822432D4` | 18 |

Every complete-object locator resolves to the expected type descriptor and
decorated class name. Every slot resolves to a generated AOT function except
the deferred renderer's one reviewed eight-byte `r3 - 4` adjustment/tail
thunk at `82585FB8`; its exact retail bytes are part of the proof. The word
after each declared surface is not another generated function, so the vtable
extent is also fail-closed rather than inferred from a convenient prefix.

## Generate the report

```powershell
python tools/discover-native-renderer-static-world-ingress.py `
  .local/generated/default `
  --image .local/analysis/default-image.bin `
  --output .local/qualification/native-renderer-static-world-ingress.json
```

The image may live in another local worktree; pass that explicit path when
needed. The generated report contains addresses and method identities only.

## What this proves

This establishes two exact title-owned candidate chains:

1. mesh to submodel to model to streamed model resource; and
2. immediate/deferred SimpleModel renderer to unified model presentation.

It gives C2 a bounded alternative to another broad draw census and makes the
next runtime probe reviewable against exact RTTI surfaces.

It does **not** yet prove that any observed instance is a building or prop,
that the graph owns a prepared procedural-model record, or that its streaming
lifetime has been captured. It therefore enables no native upload, draw,
publication, or suppression. Xenos remains authoritative.

## Next gate

The next slice must select the minimum balanced renderer or presentation
lifetime boundary from generated title flow and join an exact shared
SimpleModel object/resource identity to the existing procedural-model prepared
record. Only that joined runtime evidence may classify concrete building/prop
instances. Missing or ambiguous joins remain per-item Xenos fallback.
