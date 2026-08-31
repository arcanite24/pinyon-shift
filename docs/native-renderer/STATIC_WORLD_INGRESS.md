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

## Exact renderer-to-PM4 runtime lineage

Static instruction flow narrows the first runtime boundary further. Primary
`CSimpleModelRenderer` vtable slot 12 enters `82C4CCC8`, preserves its `r3`
renderer and `r4` render context, walks its model/submodel graph, and invokes
the direct indexed-draw emitter at `82416380`. All paths converge at
`82C4DEA0` before restoring the caller state.

A balanced passive scope now brackets those exact addresses. Entry accepts
only vtable `82001B64` and reads only the renderer vtable plus its already-used
offset-72 graph field. Both four-byte reads require guest range access and a
mapped host page. The existing exact PM4 header hooks at `82416260` and
`824162F4` attach the renderer, render context, and opaque graph identity only
when they execute synchronously inside that scope. The normal physical-header
generation join then carries the identity to the backend prepared-draw
boundary.

The cumulative scope, packet, and prepared-draw accounting is emitted every
300 census frames and once authoritatively at shutdown. Generate its report
with:

```powershell
python tools/summarize-native-renderer-static-world-runtime-join.py `
  .local/preview/logs/<session>.jsonl `
  --static .local/qualification/native-renderer-static-world-ingress.json `
  --lifetime .local/qualification/native-renderer-static-world-lifetime.json `
  --resource .local/qualification/native-renderer-static-world-resource.json `
  --streaming .local/qualification/native-renderer-static-world-streaming.json `
  --graph .local/qualification/native-renderer-static-world-graph.json `
  --session <session> `
  --output .local/qualification/native-renderer-static-world-runtime-join.json
```

`--allow-checkpoint` may diagnose an interrupted run, but checkpoint-only
evidence never proves session exit or permits admission. Even a clean final
join proves generic SimpleModel ownership, not concrete building/prop identity
or streaming lifetime. Native upload, draw, publication, and suppression stay
disabled until those next exact gates are closed.

The renderer lifetime and owned graph field are now independently proved in
[`STATIC_WORLD_LIFETIME.md`](STATIC_WORLD_LIFETIME.md). The runtime join
requires a completed renderer generation and matching graph-binding generation
before it attributes any PM4 packet. The bound graph is now independently
proved as an exact, live, registered `CSimpleModelResource` generation in
[`STATIC_WORLD_RESOURCE.md`](STATIC_WORLD_RESOURCE.md).
