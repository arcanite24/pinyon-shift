# Asynchronous isolated draw readback

NR-02E extends the one-shot authentic draw replay with an optional D3D12
readback. The private replay target is copied after the isolated draw and the
guest render targets are restored before the original Xenos draw is recorded.
The readback is associated with the submitted command list and completed only
after its fence has retired; the graphics thread does not wait for all queue
operations.

## Capture contract

Readback remains disabled unless both an exact draw signature and a new output
directory below the repository `.local` tree are supplied. The title and the
capture wrapper reject an existing destination. ReXGlue retains the readback
buffer through submission completion and invokes the title callback with the
mapped bytes, dimensions, row pitch, DXGI format, and a structured failure
status. Multisampled private targets are resolved before the copy.

The title moves the bytes into an asynchronous artifact writer. It creates a
temporary sibling directory and publishes the completed directory with one
rename after all three files have been written:

- `isolated.bin`: the full row-pitched GPU readback;
- `isolated.ppm`: the non-empty target crop converted from
  `R16G16B16A16_FLOAT` or `R8G8B8A8_UNORM`; and
- `readback.json`: signature, draw coordinates, layout, crop, hash, and safety
  metadata.

Captured signature, frame, and draw identifiers are frozen when the request
is submitted. Later census observations therefore cannot relabel the
asynchronous completion.

## Safety properties

This diagnostic path does not present the private target and exposes no draw
suppression API. Allocation, resolve, map, layout, or artifact failures are
reported as structured events while the original guest draw proceeds. Every
success and failure record declares Xenos as output authority and suppression
as ineligible.

## Qualification run

Launch the installed AppData save with a fresh destination:

```powershell
$stateRoot = Join-Path $env:LOCALAPPDATA `
    'PinyonShift\source\0.1.0\.local\preview'
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot $stateRoot `
  -Scene open_world_day `
  -IsolatedDrawSignature 747837906D0BF484 `
  -IsolatedDrawDir `
    '.local\qualification\native-renderer-isolated-readback' `
  -Json
```

The clean AppData-backed qualification completed on 2026-08-28 as session
`20260828T105842Z-p39620`. Signature `747837906D0BF484` was replayed at frame
4593, draw 117. Its 640 by 8192 `R16G16B16A16_FLOAT` target produced a
41,943,040-byte readback and a non-empty 512 by 280 crop. The raw artifact
SHA-256 was
`D2EBD1E257C1033E8D3D133FCBB67DE71DA6679CE87303BD16384C2C17201D40`.
Visual inspection identified the expected sky, cloud, and horizon/fog layer.

The AppData save reached the festival open world with normal Xenos output.
The log recorded `armed_with_readback`, `recorded`, and `captured` for the same
signature, frame, and draw, with no fatal, crash, device-loss, rejected, or
failed events. The process exited normally with code zero.

This milestone proves asynchronous extraction of a real private native draw
without disturbing displayed output. It does not yet claim visual equivalence
with an external reference capture; comparison tooling and broader pass
coverage remain later NR-02E work.
