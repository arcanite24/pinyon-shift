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

The next batched AppData run must determine the title's matrix convention from
observed values and prove a unique, tolerance-bounded spatial match against the
catalog. Ambiguous, absent, or out-of-bounds matches must remain unclassified.
Only then can a prepared draw claim a collision-prop or gameplay-object class.
Asset-key hashes may strengthen that join, but spatial proximity alone is not
accepted when multiple catalog entries remain possible.

Until that gate passes, `building_or_prop_instance_identity_proved` remains
false. Xenos stays authoritative; native admission, publication, and
suppression remain disabled.
