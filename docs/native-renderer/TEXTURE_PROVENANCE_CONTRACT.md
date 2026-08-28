# Texture provenance contract

NR-02 texture qualification is an opt-in, exact-signature diagnostic. It
establishes bounded source-content stability for a selected candidate; it does
not establish visual identity, prove that a resource is never GPU-produced, or
authorize a native upload, draw, or Xenos suppression.

## Runtime boundary

ReXGlue patch `0056-graphics-texture-layout-observer.patch` adds calculated
base and mip allocation lengths to the existing bounded draw observation. The
layout is accepted only while the referenced fetch constant is currently a
texture. No guest address is dereferenced by ReXGlue, and invalid or stale
fetch constants leave the layout-valid bit clear.

The title reads texture payload only when
`PINYON_SHIFT_NATIVE_RENDERER_TEXTURE_SCAN_SIGNATURE` is an exact 16-digit
candidate signature and a prepared draw matches it. The scanner is
once-per-process and rejects the complete scan before any read unless every
resource satisfies all of these constraints:

- one through four texture resources;
- a valid observed layout and a nonzero base allocation;
- no resource larger than 16 MiB;
- no aggregate payload larger than 32 MiB; and
- every base and mip range contained in the guest physical aperture.

Successful scans hash the bounded base and mip ranges with FNV-1a. They emit
addresses, byte counts, and hashes to diagnostics, but persist no payload
bytes. The code does not decode, upload, bind, draw, or suppress anything.
Xenos renders and presents the frame.

Use the capture wrapper to arm the exact-signature scan:

```powershell
.\tools\capture-native-renderer-census.ps1 `
  -StateRoot $stateRoot `
  -Scene open_world_day `
  -TextureScanSignature FA45AAFDC22C8625
```

Summarize at least two independent sessions, then build the cross-capture
contract:

```powershell
python .\tools\build-native-texture-provenance.py `
  .\.local\native-renderer\candidate\run-1-census.json `
  .\.local\native-renderer\candidate\run-2-census.json `
  --signature FA45AAFDC22C8625 `
  --output .\.local\native-renderer\candidate\texture-provenance.json
```

The builder requires the same successful exact-signature scan, fetch-constant
set, byte lengths, and hashes in every input. Address relocation is reported
but is not required: deterministic allocation addresses are not evidence
against content stability. The resulting `source_texture_candidate` verdict
still carries `visual_identity_confirmed: false` and
`dynamic_render_target_exclusion_required: true`.

## Local qualification — 2026-08-28

Two AppData-backed captures of candidate `FA45AAFDC22C8625` produced the same
bounded texture set:

| Session | Fetch | Base bytes | Base hash |
| --- | ---: | ---: | --- |
| `20260828T074051Z-p9108` | 0 | 16,384 | `813168E347A20D13` |
| `20260828T074051Z-p9108` | 2 | 16,384 | `A1341C9AE209EB41` |
| `20260828T080034Z-p41528` | 0 | 16,384 | `813168E347A20D13` |
| `20260828T080034Z-p41528` | 2 | 16,384 | `A1341C9AE209EB41` |

Neither texture has a separate mip allocation. Both captures used the same
guest addresses, so relocation remains unproven; the content and allocation
shape are stable across independent processes.

The first run also exposed a stale-fetch safety bug after the successful scan:
the layout observer passed a fetch constant that was no longer typed as a
texture into `TextureInfo::Prepare`, causing an integer divide-by-zero. The
observer now requires `FetchConstantType::kTexture` before layout calculation.
The rebuilt second run passed the same single-player transition, reached the
saved festival scene, emitted the matching scan at frame 4,352, and exited
normally with code zero.

This evidence advances the candidate through static-content fingerprinting
only. Visual identification and dynamic render-target exclusion remain open,
and Xenos authority remains mandatory for subsequent isolated replay work.
