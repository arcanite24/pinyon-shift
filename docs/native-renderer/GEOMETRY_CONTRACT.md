# Native geometry contract

NR-02B begins with a deterministic metadata contract, not an upload path. The
contract turns one shortlisted draw into explicit vertex declaration and bounds
facts while Xenos remains the only renderer.

## Inputs and limits

ReXGlue patch `0053-graphics-vertex-declaration-observer.patch` extends the
default-off draw observer with:

- VGT vertex index offset, minimum, and maximum registers;
- the minimum and maximum index count observed for a recurring candidate;
- up to 32 decoded vertex attributes; and
- an explicit attribute-overflow marker.

Each attribute reports only shader/fetch metadata: binding and fetch identity,
word offset and stride, Xenos data format, required fetch-word mask, exponent
and signed-RF controls, result mapping, and instruction flags. The callback
does not translate a guest address, read an index or vertex byte, upload data,
submit a native draw, or suppress Xenos work.

## Deterministic planner

Build a contract from a candidate-selection document:

```powershell
python .\tools\build-native-geometry-contract.py `
  .\.local\native-renderer\candidate\selection.json `
  --output .\.local\native-renderer\candidate\geometry-contract.json
```

The planner requires exactly one binding for the initial candidate, normalizes
its physical address with `address & 0x1FFFFFFF`, validates attribute extents
against the stride, decodes every supported Xenos vertex format, endianness,
fetch flag, result target and swizzle, independently recomputes the required
word mask, applies the 24-bit VGT offset and clamp semantics, and
proves the required non-indexed byte range fits the observed fetch allocation.
It rejects 24-bit index wrap, negative offsets, empty word masks, stride
disagreement, unknown formats, aperture crossing, and undersized allocations.

For indexed metadata, the planner also decodes 16/32-bit index format and all
four Xenos endianness modes, normalizes the DMA base, and proves the allocation
can contain the requested number of indices before permitting a later scan.
The VGT DMA base already identifies the draw's start index; VGT index offset is
the base-vertex term applied after the index value is loaded.

Indexed draws are intentionally reported as `requires_index_scan`; their bounds
cannot be proven without a later, separately bounded payload-read step. Every
contract carries explicit false values for guest payload reads, native upload,
native draw, and suppression, plus true Xenos authority.

## Bounded index-scan qualification

The later payload-read step is now available as an exact-signature diagnostic:

```powershell
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot $stateRoot `
  -Scene open_world_day `
  -IndexScanSignature FA45AAFDC22C8625
```

The scanner is disabled unless a 16-digit signature is supplied. It attempts
that signature once per process, accepts only DMA-indexed draws with one vertex
binding, and rejects unknown formats, invalid clamp state, undersized
allocations, physical-aperture crossings, more than 1,048,576 indices, or more
than 4 MiB. It reads no vertex or texture payload. Index decoding matches the
Xenos 16/32-bit endianness rules, masks values to 24 bits, excludes enabled
primitive-reset markers, and applies the VGT base offset and min/max clamp.
Only decoded bounds and a hash are logged; payload bytes remain local.

Two summarized scan captures may be supplied to the planner:

```powershell
python .\tools\build-native-geometry-contract.py `
  .\.local\native-renderer\candidate\selection.json `
  --signature FA45AAFDC22C8625 `
  --index-census `
    .\.local\native-renderer\candidate\scan-1-census.json `
    .\.local\native-renderer\candidate\scan-2-census.json `
  --output .\.local\native-renderer\candidate\geometry-contract.json
```

The planner requires one successful scan in each of at least two captures,
stable decoded payload hash, bounds, and reset state, matching index format and
endianness, and a vertex byte range that fits the signature-bound allocation.
It still emits false native-upload, native-draw, and suppression gates.

## Advancement gate

This slice is ready to merge when a clean build and AppData-backed run confirm
the selected candidate emits a stable declaration and the planner produces a
bounded contract. That is evidence for the next isolated upload/replay slice,
not permission to render or suppress the authentic draw.

## Local qualification — 2026-08-28

The 53-patch Release build completed from a freshly prepared ReXGlue tree. A
long AppData-backed `open_world_day` run (`20260828T045536Z-p1616`) exited
through the normal window-close path after 37,608 frames and 4,821,916 observed
draws. Its performance capture covered 1,221.86 seconds: median frame time was
33.232 ms (30.091 FPS), presentation cadence was 59.999 Hz, and there were no
presentation deadline misses. The census reported zero draw, resolve-target,
or resolve-page overflow and no crash, error, or device-loss event.

After the index-allocation fields were added, the exact final executable
(SHA-256 `3FF110A72800A6EC0AEF121296F6A3D3A9D8CA53B733FFFCD191AD5B3855C4B5`)
ran another 2,899-frame AppData confirmation (`20260828T051716Z-p1508`). It
also exited normally, recorded zero errors and deadline misses, and preserved
Xenos authority throughout.

The deterministic selector compared both captures and found one provisional
geometry-contract candidate, signature `6263AD066A342AFE`, with the same exact
prepared shader pair in both runs. It is a non-indexed rectangle-list draw with
24 vertices, one 16-byte binding, two `32_32_FLOAT` attributes (the second an
inherited mini-fetch), and one texture. The planner independently derived a
384-byte requirement from the declaration and VGT state, exactly matching the
384-byte observed allocation. Its generated safety record keeps guest payload
reads, native uploads, native draws, and suppression disabled.

This candidate has only two observations and still needs visual and static
texture-provenance review. It validates the declaration and bounds machinery;
it is not yet the approved authentic draw for NR-02E comparison.

## Indexed candidate qualification — 2026-08-28

Patch `0055-graphics-index-reset-observer.patch` adds the reset index and enable
state needed to scan indexed geometry precisely. Two AppData-backed
`open_world_day` sessions scanned candidate `FA45AAFDC22C8625` and exited
normally:

| Session | Frame | Indices | Bytes | Decoded range | Hash |
| --- | ---: | ---: | ---: | ---: | --- |
| `20260828T070848Z-p13800` | 3,004 | 9,300 | 37,200 | 0–1,616 | `76F4D9C9DFE1E128` |
| `20260828T071104Z-p37760` | 3,127 | 9,300 | 37,200 | 0–1,616 | `76F4D9C9DFE1E128` |

Both captures observed reset index `0000FFFF` enabled with zero reset markers.
The guest index and vertex addresses relocated between processes, while the
decoded payload and bounds remained identical. With a 32-byte stride and
32-byte maximum attribute extent, vertex 1,616 requires exactly 51,744 bytes,
matching the observed allocation exactly. The generated contract is therefore
`bounded_index_scan` and validated across two captures. This closes the guest
index/vertex bounds gate only; texture provenance, visual identification,
native upload, native drawing, and suppression remain unapproved.

The captures contained 4,134 and 4,364 performance samples, measured 31.885
and 31.653 median FPS, reported zero presentation deadline misses, and emitted
no crash, error, or device-loss event. The one-time 37,200-byte diagnostic read
did not alter Xenos rendering authority.

## Prepared-signature refresh — 2026-08-28

The prepared-pipeline observer intentionally changed the candidate identity.
Two new AppData-backed captures therefore rescanned revised signature
`747837906D0BF484` rather than reusing the historical payload result:

| Session | Frame | Index address | Vertex address | Decoded range | Hash |
| --- | ---: | ---: | ---: | ---: | --- |
| `20260828T084949Z-p36548` | 2,847 | `1426B30C` | `1425E8EC` | 0–1,616 | `76F4D9C9DFE1E128` |
| `20260828T085323Z-p43944` | 2,953 | `1428730C` | `1427A8EC` | 0–1,616 | `76F4D9C9DFE1E128` |

Both scans decoded 9,300 uint32 indices from 37,200 bytes, observed no
primitive-reset marker, and independently reproduced the exact 51,744-byte
vertex bound. The relocated index and vertex allocations demonstrate that the
contract is content- and layout-bound rather than tied to one process address.
Both processes exited normally with no error, crash, or device-loss event.
Native upload, native drawing, and suppression remained disabled.
