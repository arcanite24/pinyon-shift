# Track-world reference composition census

Status: implemented; runtime qualification batched with scope spatial census

## Why this is a stronger transform lead

Retail instruction flow in `8240E7B0` proves two complete 64-byte matrices
immediately before the exact unified track render-model dispatch:

- `r22` is the live object/reference input matrix; and
- `r5` is the fully composed stack matrix passed to constant writer `82435E78`.

Earlier vehicle work correctly rejected both as absolute vehicle poses. Phase
C1 subsequently proved the same function's root and child are the unified
track render-model instance/model pair. The matrices are therefore useful
track reference-space evidence even though they were not a vehicle bridge.

The raw child/descriptor spatial census tests for an authored absolute matrix.
This companion census tests the more likely alternative: a local track-section
matrix becomes an authored world position only after composition with one of
these title-proved reference matrices.

## Exact runtime join

The existing hook at `8240EB5C` stages both finite matrices in thread-local
storage. Each later exact scope entry at `8240EC80` reuses the current stage
only after the unified instance/model vtables and type-21 descriptor predicates
pass. Static control flow proves one staged pair can feed many downstream exact
scopes before the next function invocation overwrites it. Invalid roots cannot
publish a reference snapshot, and ordinary calls never inherit an accepted
track identity.

A fixed 2,048-entry table is keyed by exact child/descriptor addresses, exact
child/descriptor content hash, and both matrix hashes. It retains the numeric
matrices and call/frame coverage.
Detailed entries are emitted only at clean final shutdown. Missing same-thread
stages, invalid ranges, non-finite matrices, and table overflow are independently
counted. No stack pointer is retained after the synchronous copy.

## Offline composition qualifier

After the next meaningful AppData run:

```powershell
python tools/classify-native-renderer-track-reference-composition.py `
  <session.jsonl> `
  --catalog .local/qualification/native-renderer-static-world-instance-catalog.json `
  --output .local/qualification/native-renderer-track-reference-composition.json
```

The classifier joins each reference snapshot to the stable child/descriptor
snapshot with the same exact addresses. For every finite local 16-word window,
it evaluates both reference sources, both multiplication orders, and both
supported title matrix conventions. Each candidate translation is matched to
the 24,025-entry authored spatial catalog.

Qualification requires complete lifecycle and call accounting, zero missing
stage or overflow, every snapshot mapping unambiguously, at least eight
distinct catalog instances including a collision prop, and exactly one
local-source/offset/reference/order/convention mapping. A negative result
closes both absolute and reference-composed interpretations of these bounded
structures before C1 moves farther upstream.

## Safety

- Both 64-byte ranges are statically proved live at the existing hook.
- Guest state and title control flow are unchanged.
- Xenos remains authoritative.
- Native upload, publication, admission, and suppression remain disabled.
- Runtime validation is batched with the pending scope census.
