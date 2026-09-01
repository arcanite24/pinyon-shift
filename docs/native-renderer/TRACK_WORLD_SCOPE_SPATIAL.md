# Track-world scope spatial census

Status: implemented; runtime qualification deliberately batched

## Purpose

The exact indirect track command reaches prepared draws, but its prepared
vertex-constant windows do not correlate with title-authored world positions.
The next narrow C1 boundary is therefore upstream: the already-validated
64-byte track child and 248-byte type-21 descriptor that define each exact
command scope.

This census tests whether either title-owned structure carries a stable
four-by-four numeric transform window. It does not add another object walk,
speculative pointer dereference, broad draw census, or shader-state guess.

## Runtime contract

At exact scope entry, after the existing child and descriptor bounds, type, and
flag checks succeed, the observer retains one numeric snapshot per exact
child/descriptor address pair. The fixed 1,024-entry table records:

- all 16 child words and all 62 descriptor words;
- snapshot hash and variation count;
- exact call and first/last-frame coverage; and
- explicit table overflow.

The observer reads no new guest range: both arrays were already copied for the
exact scope and world-resource classifier. Detailed entries are emitted once,
only during clean final shutdown. No plaintext identity or asset payload is
exported.

## Offline classifier

After the next meaningful batched AppData run:

```powershell
python tools/classify-native-renderer-track-scope-spatial.py `
  <session.jsonl> `
  --catalog .local/qualification/native-renderer-static-world-instance-catalog.json `
  --output .local/qualification/native-renderer-track-scope-spatial.json
```

The classifier requires one complete lifecycle, one final summary, exact entry
and call accounting, zero overflow, and stable snapshots. It interprets every
finite consecutive 16-word window under the two supported title matrix
conventions and compares translations with the existing static-world catalog.
A mapping qualifies only when every retained scope snapshot matches exactly one
catalog position within 0.05 units, at least eight distinct catalog instances
match, a collision prop is included, and exactly one source/offset/convention
group passes.

An incomplete report is a useful negative result: it closes these raw numeric
windows and sends C1 to the next upstream title-owned section carrier. It never
widens native admission or suppression.

## Safety

- Xenos output remains authoritative.
- Guest state and control flow are unchanged.
- Native upload and drawing remain disabled for this evidence.
- Suppression remains disabled.
- Capture uses the installed AppData save in place.
