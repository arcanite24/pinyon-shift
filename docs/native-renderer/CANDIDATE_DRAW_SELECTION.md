# Candidate draw selection

NR-02 candidate selection is a local, evidence-producing workflow. It does not
read guest buffer contents, submit native work, or make a draw eligible for
suppression. Xenos remains authoritative.

## Bounded draw state

ReXGlue patch `0051-graphics-draw-candidate-state.patch` extends the existing
default-off observer with the metadata needed to reject unsuitable first
draws:

- index format and endianness;
- at most eight vertex bindings, with fetch identity, address, byte range,
  stride, and endianness;
- color write masks and four blend-control registers;
- depth, rasterizer, and vertex convention registers; and
- an explicit overflow bit when a shader exceeds the vertex-binding bound.

The observer still runs immediately before the unmodified `IssueDraw` call.
It borrows no bytecode and serializes no vertex, index, texture, constant, or
render-target contents. The disabled path remains one null callback check.

The existing NR-00 pass signature remains byte-for-byte stable. A separate
candidate signature includes layout shape, index interpretation, query and
memexport state, resolved-input observation, and the captured pipeline state.
The census emits at most 32 candidate records per 300-frame window. Buffer
addresses are reported in the local sample but deliberately do not identify
the recurring candidate signature.

Patch `0052-d3d12-prepared-draw-observer.patch` adds a second default-null,
metadata-only callback after successful D3D12 pipeline configuration. It joins
the guest vertex/pixel hashes to the exact ReXGlue specialization masks used by
that prepared draw. The title records at most 1,024 unique pairs. The selector
requires one pair to recur in every supplied capture and verifies that exact
identity exists in the local shader manifest; it never guesses among multiple
translations of the same guest hash.

Patch `0053-graphics-vertex-declaration-observer.patch` keeps that observer
passive while adding the bounded declaration needed for NR-02B. It records at
most 32 vertex attributes plus the VGT index offset/minimum/maximum registers
and the observed index-count range. Attribute metadata includes the fetch
constant, word offset and stride, data format, required word mask, result
mapping, and instruction flags. Overflow is explicit. Neither this patch nor
the title-side contract builder dereferences a guest address.

## Repeated-capture shortlist

Capture the same marked scene at least twice while also collecting the local
shader manifest:

```powershell
$capture = '.\.local\native-renderer\candidate\run-1'
.\tools\capture-native-renderer-census.ps1 `
  -Scene open_world_day -ShaderCaptureDir $capture
```

After each normal exit, summarize the corresponding diagnostic session with
`summarize-native-renderer-census.py`. Then produce the shortlist:

```powershell
python .\tools\select-native-renderer-candidate.py `
  .\.local\native-renderer\candidate\run-1-census.json `
  .\.local\native-renderer\candidate\run-2-census.json `
  --shader-manifest `
  .\.local\native-renderer\candidate\run-1\shader-manifest.json `
  --output .\.local\native-renderer\candidate\selection.json
```

The selector requires a signature and exact prepared shader pair in every
input capture. It accepts both indexed and non-indexed authentic draws because
the NR-02 candidate criteria do not require an index buffer. It rejects missing
or ambiguous prepared pairs, shader-pack misses, blending, query or memexport
state, observed resolved-target inputs, more than one vertex binding, more than
four or fewer than one texture resource, and either bounded-observer overflow.
Results are ordered deterministically by recurrence and draw count.

The resulting selection can be converted into a metadata-only geometry
contract as described in [GEOMETRY_CONTRACT.md](GEOMETRY_CONTRACT.md). An
indexed candidate is retained by the selector, but the initial contract marks
it as requiring a later bounded index scan rather than reading payload data.

## Local qualification — 2026-08-28

The clean 52-patch Release build produced executable SHA-256
`AE63C436A34B56AD4775FE5B5669F6D1E8A63F50B96203DB0B8D246CFD191083`.
Two consecutive `open_world_day` captures against the installed `0.1.0`
AppData save exited normally:

| Session | Draws | Candidate records | Prepared shader pairs |
| --- | ---: | ---: | ---: |
| `20260828T040945Z-p40816` | 2,070,384 | 75 | 274 |
| `20260828T041037Z-p40152` | 2,783,339 | 85 | 286 |

The selector found one repeatable candidate, signature
`E184D75768958828`, across 6,183 observed draws. It uses vertex shader
`3BC346726C1C2535` with specialization `000000000000000F` and pixel shader
`9584B309533EF6C9` with specialization `00000000000E000F`. Its bounded sample
is an opaque, non-indexed primitive with one 40-byte vertex binding and one
texture fetch. The exact shader identities exist in the first capture's local
manifest.

This result selects the subject for visual identification and NR-02B data
validation; it does not establish static-texture provenance, visual parity, or
suppression safety. Xenos rendered and presented both qualification runs.

The final close-path build produced executable SHA-256
`C2A49BAFBEAFFB1B0B414F224718F05F3BA0DA6C1E13AECA46A3A289CF4BE903`.
Session `20260828T041356Z-p41140` verified that a normal window close flushes
four candidate windows and a 231-pair prepared-shader summary with zero
overflow. It exited normally with no error event and Xenos authority intact.

`metadata_shortlist_only` is not a rendering-safety verdict. In particular,
failure to observe a resolved input does not prove that a texture is static.
The selected draw still requires visual identification, dependency review,
guest bounds validation, and isolated comparison before NR-02 can advance to
native execution.

## NR-02B signature revision

Patch `0053` intentionally adds VGT range and full vertex-declaration metadata
to the candidate signature. Therefore pre-`0053` signatures, including
`E184D75768958828`, are historical identities and cannot be compared directly
with new captures.

Two post-`0053` `open_world_day` captures selected one provisional geometry
candidate, `6263AD066A342AFE`. Its exact declaration and allocation bounds are
recorded in [GEOMETRY_CONTRACT.md](GEOMETRY_CONTRACT.md). The candidate remains
`needs_visual_and_dependency_review`; the new selection proves repeatable
metadata and an exact shader specialization, not visual suitability or static
texture provenance.

## NR-02C draw-state extension

Patch `0054` adds the used constant registers and raw texture/sampler inputs to
each candidate summary. Constant or texture-state overflow is an automatic
rejection. The selector carries the first bounded snapshot from each inventory
and its draw-state hash. Decoding and the safety boundary are documented in
[DRAW_STATE_CONTRACT.md](DRAW_STATE_CONTRACT.md).

Two post-`0054` captures initially selected candidate `08810649442C4213` as the
sole bounded metadata match, with an identical draw-state hash in both runs.
Cross-checking its decoded texture address against the full resolve-target
inventory then identified `0x1C149000` as a known resolve destination. The
candidate is therefore rejected as a dynamic render-target consumer and does
not advance to PSO construction.

The selector now checks every captured base and mip address against every
emitted resolve range in each input inventory. This is deliberately stricter
than the draw-window `resolved_input` bit: a missed timing correlation can no
longer turn absence of a dependency event into static-texture evidence.

## Prepared-specialization correlation

Candidate aggregation is deferred from the generic pre-draw observation until
the synchronous D3D12 prepared-draw callback. The callback supplies the exact
effective vertex and pixel shader identities plus their specialization masks.
This matters when an active guest pixel shader is omitted from the prepared
pipeline because rasterization is disabled, and when one guest shader pair has
multiple render-target specializations.

The specialization masks are part of the candidate signature and are emitted
with every candidate record. Selection now requires the exact pair to repeat in
every capture, appear in each prepared-draw inventory, and exist in the local
shader manifest. It no longer guesses from all specializations seen for a guest
shader pair.

AppData-backed sessions `20260828T061406Z-p33972` and
`20260828T061541Z-p41620` reached more than 2,100 frames and exited normally.
Both reported zero prepared callbacks without a corresponding generic draw
observation, zero observer overflow, and 22 prepared shader pairs. Exact
correlation recovered four repeatable candidates under the existing
zero-or-one-texture gate; all four are textureless. Two additional opaque,
one-binding candidates have three non-resolved texture inputs and remain
rejected by the current bounded-complexity gate pending an explicit scope
decision.

## Bounded texture-set qualification

The NR-02 static-source requirement makes a textureless draw unsuitable for the
first isolated replay even when its shader and geometry metadata are otherwise
simple. The selector now requires one through four texture resources. This
keeps the first replay bounded while admitting common material sets without
weakening the resolve-range exclusion or any Xenos-authority gate.

Two AppData-backed `gameplay_candidate` captures navigated through the title
screen into the same open-world save and exited normally:

| Session | Frames | Draws | Candidate records | Median FPS | 1% low FPS |
| --- | ---: | ---: | ---: | ---: | ---: |
| `20260828T062404Z-p40136` | 9,191 | 18,294,006 | 117 | 30.333 | 19.602 |
| `20260828T062956Z-p33312` | 6,573 | 14,902,074 | 115 | 30.570 | 19.443 |

Exact cross-capture selection produced five bounded candidates. Three use the
same opaque quad-list shader pair, one 40-byte binding, and one non-resolved
512 by 512 tiled `DXT4_5` texture. They are better static-source leads than the
front-end candidates, but the geometry planner correctly rejects their current
snapshots: a four-vertex quad needs 160 bytes while the observed fetch exposes
one 40-byte record. Quad expansion or instancing semantics must be understood
before any guest payload read.

The remaining two candidates are the previously observed three-texture,
full-screen YUV-style compositor family. Their non-resolved addresses satisfy
the mechanical gate, but their render-sized planes and conversion constants
make them inappropriate for the first authentic world draw. No candidate from
this qualification advances to PSO construction. Xenos remained authoritative
throughout both runs, and suppression remains disabled.
