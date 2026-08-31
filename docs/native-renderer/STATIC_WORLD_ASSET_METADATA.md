# Static-world asset-reference metadata

Status: bounded resource-key and effect/texture reference paths proved;
passive hashed runtime lineage implemented; qualification pending

## Purpose

The exact `CModelPresentation` owner and `CSimpleModelResource` identity do not
by themselves distinguish a building from a prop. This checkpoint follows the
smallest bounded metadata surface that can supply stable instance categories,
without opening game asset files or exporting guest strings.

## Exact metadata paths

`tools/discover-native-renderer-static-world-asset-metadata.py` locks these
retail instruction and image contracts:

- initialization stores the presentation name in the 28-byte string at owner
  offset 16 and passes those exact bytes to resource binder `82C48038`, which
  stores the resulting `CSimpleModelResource` at owner offset 148;
- preparation reads a 16-bit count at resource offset 128 and a pointer at
  offset 124, walks 28-byte string records, removes the exact `.fx` suffix,
  and resolves the resulting effect references through `82C39B78`; and
- preparation also walks the 28-byte string vector at resource offset 288,
  extracts the exact `Id=` component, constructs paths with
  `%s%stextures\%s`, and resolves them through `82C39730`.

This proves stable resource-key, effect-reference, and texture-reference
metadata surfaces. It does not prove that any particular key is a building or
a prop, nor does it prove mesh vertex/index layout.

## Generate the report

```powershell
python tools/discover-native-renderer-static-world-asset-metadata.py `
  .local/generated/default `
  --image .local/analysis/default-image.bin `
  --output .local/qualification/native-renderer-static-world-asset-metadata.json
```

## Runtime boundary

The passive runtime observer reads only these proved fields. It emits the
FNV-1a hash and length of the presentation key plus effect/texture counts,
then carries them through the renderer, physical PM4 packet, and prepared-draw
lineage. Plaintext names are never emitted. Exact, empty, faulted, joined, and
missing-join outcomes are independently accounted and the qualifier fails
closed on any joined draw without valid metadata.

The combined C1/C2 AppData run remains intentionally batched. Xenos remains
authoritative; this checkpoint enables no native admission or suppression.
