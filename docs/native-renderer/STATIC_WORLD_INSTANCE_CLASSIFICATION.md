# Static-world instance classification

Status: title-authored collision-prop and gameplay-object spatial catalogs
built; exact runtime transform join implemented; category join not yet proved

## Purpose

The generic SimpleModel graph and presentation key identify a concrete rendered
instance but do not label it as a building or prop. The Colorado ribbon ships
two title-authored spatial inventories that supply independent categories:

- `CollObjs.xml` contains collision-prop identities, positions, and orientation
  axes; and
- `GameObjs.xml` contains gameplay-object identities, positions, and
  orientation axes.

`tools/build-native-renderer-static-world-instance-catalog.py` turns those
inputs into a read-only, payload-free spatial catalog. It hashes every identity
field with FNV-1a 64, retains only numeric position/orientation metadata, and
records a SHA-256 digest and count for each source. It never exports plaintext
asset names or game payload bytes.

The current retail Colorado inputs produce 24,025 entries: 21,877 collision
props and 2,148 gameplay objects. This proves the availability of authoritative
content categories, not their relationship to runtime draws.

## Build the local catalog

```powershell
python tools/build-native-renderer-static-world-instance-catalog.py `
  --collision .local/game/base/media/tracks/colorado/Ribbon_00/CollObjs.xml `
  --gameplay .local/game/base/media/tracks/colorado/Ribbon_00/GameObjs.xml `
  --output .local/qualification/native-renderer-static-world-instance-catalog.json
```

The output stays below `.local`; it is evidence, not a checked-in game-data
derivative.

## Runtime boundary

Retail instructions prove that `CModelPresentation` stores its complete
64-byte transform at offset 80 and passes it through renderer slot 6
(`82C4C568`) to renderer offset 128 before the exact slot-12 draw. The passive
observer now carries those 16 numeric words and their hash through the
renderer, physical PM4 packet, and prepared-draw provenance.

`tools/summarize-native-renderer-static-world-instance-classification.py`
implements the next fail-closed gate. It evaluates the two plausible 4x4
translation layouts independently, uses a 0.05-world-unit spatial bound, and
requires at least eight distinct prepared-draw transforms. Every observed
transform must match exactly one catalog entry, exactly one matrix convention
must pass, and at least one collision prop must be present. Ambiguous, absent,
non-finite, or unsafe observations reject the whole report. The input session
must also have a unique clean process lifecycle and a complete static-world
runtime summary.

```powershell
python tools/summarize-native-renderer-static-world-instance-classification.py `
  <session.jsonl> `
  --catalog .local/qualification/native-renderer-static-world-instance-catalog.json `
  --output .local/qualification/native-renderer-static-world-instance-classification.json
```

This matcher is implemented but cannot qualify until a build containing the
new transform observer completes the deferred AppData run. Asset-key hashes
may later strengthen the join, but spatial proximity is never accepted when
multiple catalog entries remain possible.

Until that run passes, `building_or_prop_instance_identity_proved` remains
false. Even a successful category report does not independently enable native
admission, publication, or suppression; Xenos stays authoritative.
