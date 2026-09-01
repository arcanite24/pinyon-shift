# Unified track-presentation pass census

Status: implemented; runtime qualification batched with the next Phase C run

## Why the pass boundary moved

Clean AppData session `20260901T034815Z-p46676` proved the corrected spatial
accounting: 485 exact unified track scopes produced 140 content snapshots and
167 reference-composition snapshots with zero missing stages, overflow, or
accounting faults. Neither the 96 raw child/descriptor candidates nor the 384
reference-composition candidates uniquely matched the 24,025-entry authored
spatial catalog. Those transform interpretations are closed.

The same run produced 732 exact prepared draws. Every candidate passed the
geometry, constants, textures, query, memexport, and pipeline gates and failed
only the attachment-shape gate. Zero exact track draws entered the native
world workset. The existing slot-79 path is therefore not yet proved to be the
opaque road/terrain color pass that the visible prototype needs.

## Static pass ownership

Retail RTTI identifies vtable `82243774` as
`Presentation_Unified::CTrackPresentation`. Its adjacent slots are:

| Slot | Function |
|---:|---:|
| 78 | `82DEEEE0` |
| 79 | `8240E7B0` |
| 80 | `82DEF2B0` |
| 81 | `82DEADE0` |

Slot 79 is the previously followed exact render-model route. The other three
functions are title-owned neighbors on the same unified presentation object;
they are stronger opaque-pass candidates than another untyped global draw
census.

## Runtime contract

Balanced entry and common-exit hooks count each slot independently. Entry is
accepted only when `r3` has the exact unified track-presentation vtable.
Invalid roots, overlaps, and exits without entries are reported separately.
The final summary is
`native_renderer.discovery.track_presentation_pass_summary`.

The exact slot-79 prepared-layout entries also export the backend attachment
bitmask, five numeric formats, and prepared-pipeline flags already present in
the observer. This distinguishes depth-only, color-only, paired, and unusual
target shapes without copying a guest or GPU payload.

The next batched AppData run must first identify which adjacent slots are live
and reconcile slot 79's exact target shapes with its 732 render-target-only
rejections. Packet/prepared lineage will then be extended only through the
live color-producing slot. A depth-only slot may feed the native shadow slice,
but it cannot satisfy C1 opaque world coverage.

## Safety

- The hooks read only the presentation vtable already live at entry.
- Prepared target data is bounded numeric metadata from the existing backend
  observer.
- Guest state, title control flow, Xenos draws, and output are unchanged.
- Native admission and suppression remain disabled by this census.
