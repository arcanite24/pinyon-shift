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
