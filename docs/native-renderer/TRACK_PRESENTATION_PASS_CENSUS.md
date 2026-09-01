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
`Presentation_Unified::CTrackPresentation`. Runtime qualification then proved
that calls use its exact thread-safe refcounted wrapper at vtable `82003CCC`.
Both tables have 135 entries and the wrapper carries these same adjacent
targets:

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

## Packet-to-prepared correlation

An accepted presentation slot is now attached to the existing exact
`824365B0` command-context bridge while that balanced title scope is active.
The four-bit slot mask follows the already-proved context, producer, owner,
constructor, indirect packet, and prepared-draw lineage. Final shutdown emits
one bounded entry per slot-mask, shader pair, attachment shape, and pipeline-
flag tuple. The 256-entry table has independent observation, entry, and
overflow accounting.

Build the payload-free report after the next batched run:

```powershell
python tools/summarize-native-renderer-track-presentation-passes.py `
  <session.jsonl> `
  --output .local/qualification/native-renderer-track-presentation-passes.json
```

The report reconciles process lifecycle, every balanced slot, and every
prepared target entry. It lists live slots plus depth-only, color-only, paired,
and unusual target calls per slot. A color-producing slot is still a candidate,
not an opaque-world proof; private replay and visual comparison remain the
next gate.

The next batched AppData run will identify which adjacent slots are live and
which exact prepared target shapes each produces. Lineage will be promoted
only through a live color-producing slot after visual proof. A depth-only slot
may feed the native shadow slice, but it cannot satisfy C1 opaque world
coverage.

## First pass-lineage run and receiver correction

AppData session `20260901T042139Z-p17172` reached the saved festival and
exited normally. Slot 79 made four balanced calls and slot 80 made six;
slots 78 and 81 were idle. All ten calls failed the initial receiver check,
so no prepared target inherited a pass mask. The zero-target result therefore
does not reject either live slot.

The check incorrectly treated membership in the static `82243774`
presentation vtable as a runtime receiver constraint. A first correction also
mistook the inner slot-79 render-model scope (`820019CC`) for the outer method
receiver. Controlled retry session `20260901T044525Z-p9440` resolved the
ambiguity: all four slot-79 calls and all six slot-80 calls used `82003CCC`.
Retail RTTI identifies that exact complete-object vtable as
`TRefCountedObjectThreadSafe<CTrackPresentation<Presentation_Unified>>`, and
its slots 78-81 resolve to the four already hooked AOT targets. The census now
accepts only this proved wrapper receiver for all four slots; observed runtime
activity remains limited to slots 79 and 80.

This correction still changes no renderer behavior: it only allows the
already diagnostic packet lineage to retain slot 79's identity. Xenos remains
authoritative, and native admission, publication, and suppression stay closed.

The retry exited normally with zero receiver read faults, overflow, overlap,
or lifecycle drift. It intentionally produced no prepared-target entries
because the incorrect inner-scope receiver gate rejected all ten calls. That
result closes the receiver classification rather than classifying either live
pass. The next batched run can carry both exact live slot masks into prepared
draws.

The prepared-target key also retains the already observed raw viewport,
viewport-transform control, and window scissor. The offline report decodes
only the scissor extent while preserving the raw state. The next batched run
can therefore separate main-view color, square shadow/reflection, and reduced
offscreen work even when shader and attachment formats overlap. This is
spatial-state classification only; it does not infer camera matrices or admit
a draw.

The same entry now carries the raw Xenos surface, four color-target, and depth-
target registers. These numeric registers preserve the exact EDRAM target
identity alongside attachment shape and spatial state, so one run can separate
two passes that share dimensions and formats but write different tiles. The
observer does not read target contents or change target ownership.

## Safety

- The hooks read only the exact refcounted presentation-wrapper vtable already
  live at entry.
- Prepared target data is bounded numeric metadata from the existing backend
  observer.
- Guest state, title control flow, Xenos draws, and output are unchanged.
- Native admission and suppression remain disabled by this census.
