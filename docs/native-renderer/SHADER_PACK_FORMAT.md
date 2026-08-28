# Native shader pack format

NR-02A uses a deterministic local package for host-consumable D3D12 shader
bytecode. The public repository contains this format, its builder, and shader
identity metadata only. Extracted guest shaders, translated source, DXIL, and
completed packs are locally derived artifacts and must remain under `.local`.

## Stable identity

A shader entry is identified by this ordered tuple:

1. stage: `vertex` or `pixel`;
2. the 64-bit guest shader hash reported by ReXGlue; and
3. a 64-bit specialization mask defined by the future candidate replay path.

The specialization mask is explicit even when it is zero. Runtime lookup must
never silently fall back from one specialization to another. A missing exact
identity is a coverage failure and leaves the isolated native draw unavailable;
it does not affect the authoritative Xenos frame.

## Local manifest

The builder consumes UTF-8 JSON with this shape:

```json
{
  "schema": "pinyon-shift.native-shader-pack.v1",
  "backend": "d3d12",
  "entries": [
    {
      "stage": "vertex",
      "guest_hash": "0123456789ABCDEF",
      "specialization_mask": "0000000000000000",
      "bytecode": "dxil/0123456789ABCDEF.dxil",
      "sha256": "64 hexadecimal digits"
    }
  ]
}
```

Bytecode paths must resolve inside the manifest directory. Every file must be a
non-empty DXIL container beginning with `DXBC`, must be no larger than 16 MiB,
and must match its declared SHA-256. Duplicate identities are rejected.

Build and independently verify a pack with:

```powershell
python .\tools\native-shader-pack.py build `
  .\.local\native-renderer\shader-manifest.json `
  --output .\.local\native-renderer\pinyon-shift-d3d12.pnsp
python .\tools\native-shader-pack.py verify `
  .\.local\native-renderer\pinyon-shift-d3d12.pnsp
```

## Binary layout

All integers are unsigned little-endian. The file begins with an 80-byte
header, followed by fixed 68-byte entries, followed by 16-byte-aligned DXIL
payloads.

| Header field | Type | Meaning |
| --- | --- | --- |
| Magic | 8 bytes | ASCII `PNYNSHPK` |
| Version | `u32` | `1` |
| Header size | `u32` | `80` |
| Entry size | `u32` | `68` |
| Entry count | `u32` | bounded to 65,535 |
| Index offset | `u64` | always 80 in version 1 |
| Data offset | `u64` | first byte after the fixed index |
| Data size | `u64` | complete aligned payload region |
| Content SHA-256 | 32 bytes | hash of the index and payload region |

Each entry stores an 8-bit stage, an 8-bit bytecode format (`1` for DXIL), a
zero 16-bit reserved field, guest hash, specialization mask, payload-relative
offset, payload size, and the 32-byte SHA-256 of its DXIL payload.

Entries are sorted by the complete stable identity. The builder writes through
an atomic temporary file. Verification checks the file-wide content hash,
every entry hash and range, DXIL magic, identity order, uniqueness, and all
bounded sizes before any shader is exposed to a renderer.

## Public-source and fallback rules

- Do not commit manifests containing extracted shader paths or hashes unless
  those values are independently distributable metadata approved for the
  public boundary.
- Never commit translated guest shader source, DXIL, or `.pnsp` output.
- A corrupt pack, unknown version, unsupported stage, missing identity, or
  failed hash is explicit failure. The isolated NR-02 renderer yields and
  Xenos remains authoritative.
- This package does not enable guest draw or resolve suppression.

## NR-02A qualification

Clean commit `5938136` built with all 49 ReXGlue patches and produced
executable SHA-256
`27163174F2180837FF7BCBDDA7028EA68275F70B2E38B7ED0B9B410E9107BC33`.
All 68 repository tests passed, tracked Markdown links were valid, and the
public-source boundary reported zero violations.

The builder produced the same 212-byte one-entry qualification pack regardless
of manifest order. Its SHA-256 was
`BFB4A386B4F3840048088E186E55CC6AD534F6D3AB109DA2600B7572FD3390EE`,
and an independent verify operation accepted every range and digest. Unit tests
also rejected duplicate identities, mismatched hashes, path traversal,
non-DXIL input, and content corruption.

AppData-backed session `20260828T023642Z-p41636` loaded that pack and recorded
one D3D12 entry while separately retaining Xenos output authority. Visual
inspection confirmed the normal Xenos-rendered startup sequence. The session
claimed no native frame, recorded no shader-pack failure, device removal, TDR,
validation warning, resource-state warning, or presentation deadline miss, and
exited normally. Presentation cadence was 59.994 Hz and simulation cadence was
29.209 Hz.

Recovery session `20260828T023747Z-p9136` selected a missing pack. It emitted
exactly one sanitized `validation_failed` event with `fallback=xenos`, then
recorded Xenos as output authority, claimed no native frame, and exited
normally without another error signal. Neither qualification run changed or
copied the AppData save.

Authentic local capture is documented in
[`CANDIDATE_SHADER_CAPTURE.md`](CANDIDATE_SHADER_CAPTURE.md). The capture writer
emits this manifest schema directly from validated ReXGlue translations while
keeping all shader identity and bytecode data under `.local`.
