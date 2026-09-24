# Skate 3 Recomp native-renderer sequence — 2026-09-24

This is a source-history study of the pinned local Skate 3 Recomp checkout at
`f6e0ae8` (227 commits, full local history), not a claim that its title data,
SDK patches or speedup transfer to FH1. The visible commits show the order of
public changes; they do not establish all earlier private research or elapsed
engineering time. Use the architecture as a reference, not source to transplant.

| Visible step | Primary-source evidence | What shipped at that step |
| --- | --- | --- |
| Snapshot and model discovery | [2ad56d2](https://github.com/mchughalex/skate3recomp/commit/2ad56d2d4bc457eec07fb300b664755a9b2d72e9), July 2 | A bounded frame snapshot harness recorded `RenderMesh` and sorted scene-list submissions and reconstructed guest mesh data. |
| First live replacement | [9f66afb](https://github.com/mchughalex/skate3recomp/commit/9f66afbe2a290d96e7ce5e1713b759b362a315ab), July 2 | An opt-in D3D12 output callback drew the chosen primary opaque view into the presented guest output and returned success instead of presenting the emulated frame. It used simple gray lighting and skipped skinned dynamic entities. Its mesh cache used a content fingerprint because guest addresses can be reused. |
| Basic recognizable scene | [4a2231b](https://github.com/mchughalex/skate3recomp/commit/4a2231b14deef064f00c269e5d8c3e64805ae757) and [d101dc8](https://github.com/mchughalex/skate3recomp/commit/d101dc8), July 2 | Diffuse textures, alpha-tested foliage, second UVs, skinned characters, then props, hair, normals, sky, mips and 4× MSAA followed the first live image. |
| Switch and diagnose | [7081260](https://github.com/mchughalex/skate3recomp/commit/7081260), July 5; [2dedfe1](https://github.com/mchughalex/skate3recomp/commit/2dedfe1), July 6 | A live native/emulated toggle and screenshots preceded the formal shader-parity program and offline microcode emulation. |
| Broaden appearance, then optimize | [89e78ad](https://github.com/mchughalex/skate3recomp/commit/89e78ad), [8e4db0b](https://github.com/mchughalex/skate3recomp/commit/8e4db0b) and [c613ffa](https://github.com/mchughalex/skate3recomp/commit/c613ffacc8a8f859be0c5ab256fd2207db37fbcd), July 9 | World-material and vehicle shading were expanded before a named native-renderer performance overhaul. |
| Broaden usable modes | [302ba69](https://github.com/mchughalex/skate3recomp/commit/302ba69), [ba50240](https://github.com/mchughalex/skate3recomp/commit/ba50240) and [592700b](https://github.com/mchughalex/skate3recomp/commit/592700b), July 13 | Pause menu, loading/boot flow and FMV gained native paths after gameplay rendering existed. |
| Generalize and default | [abe53a2](https://github.com/mchughalex/skate3recomp/commit/abe53a2), July 16; [404cec3](https://github.com/mchughalex/skate3recomp/commit/404cec3), July 19; [77283fe](https://github.com/mchughalex/skate3recomp/commit/77283fe), July 21 | The renderer moved to a D3D12/Vulkan abstraction, became the default with diagnostics gated, and later exposed sticky-failure fallback/retry. The [README](https://github.com/mchughalex/skate3recomp) still calls the renderer early and lists visual issues. |

The important ordering is **live replacement → recognizable gameplay →
broader appearance/modes → performance and parity work → default native**.
Skate did not make perfect material parity or a measured speedup a prerequisite
for its first in-game native frame. It did have a title-specific scene hook,
direct output takeover, a cache freshness check and an emulated fallback.
Its first renderer selected one main opaque list and omitted skinned entities;
that was a development milestone, not complete gameplay coverage.

FH1 is further along in draw ownership than Skate's first live commit: the
selected race scene has a strict frame-wide census and six owned geometry
families, and the offline/current-device diagnostic can replay them in order.
FH1 is behind at the product boundary: there is no live native output
takeover, no continuous native gameplay presentation and no retained HUD/pass
composition. The current file-backed handoff is a diagnostic, not a runtime
scene feed. Our immediate milestone should therefore be **an opt-in live
native frame using the existing owned scene**, even if its colors are crude.

The FH1 SDK seam differs from Skate's. Skate's `IssueSwap` calls a native
renderer that can return success before its compatibility gamma/FXAA path;
the current FH1 callback observes the output after compatibility processing
and cannot take over presentation. Add the smallest D3D12 output-selection
branch needed for FH1, retain the final render-test observer, and keep
compatibility available for a whole-frame fallback. Do not import Skate's
SDK fork or add Vulkan/general RHI work to the first live milestone.

The first native frame may have flat colors, absent effects and incomplete
HUD. Call it a **live pilot**, not a usable renderer. The next milestone is a
recognizable, controllable sustained race with road, vehicles, foliage,
basic material/alpha treatment and readable HUD or equivalent gameplay cues;
unsupported menus and modes may yield entirely to compatibility. Only after
that should the project optimize and use the previously declared 15% speed
and approximately 90% visual targets as qualification tests. Scene identity,
resource freshness, safe output selection and fallback are correctness
requirements from the first live frame; they are not deferred visual polish.
