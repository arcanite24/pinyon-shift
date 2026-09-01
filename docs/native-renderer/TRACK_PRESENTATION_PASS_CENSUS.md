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
presentation vtable as a runtime receiver constraint. Existing qualified
evidence inside slot 79 already identifies its live `r3` receiver as unified
track render-model instance vtable `820019CC`. Slot 79 now accepts only that
proved runtime type. A bounded receiver-signature census records the readable
`r3` vtable for every neighboring slot with exact observation, entry,
read-fault, and overflow accounting. Slots 78, 80, and 81 remain unaccepted
until their runtime receiver types are captured and classified.

This correction still changes no renderer behavior: it only allows the
already diagnostic packet lineage to retain slot 79's identity. Xenos remains
authoritative, and native admission, publication, and suppression stay closed.

## Safety

- The hooks read only the presentation vtable already live at entry.
- Prepared target data is bounded numeric metadata from the existing backend
  observer.
- Guest state, title control flow, Xenos draws, and output are unchanged.
- Native admission and suppression remain disabled by this census.
