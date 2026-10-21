# Rally free-roam investigation (#490)

Rally free roam is **not a qualified player feature**. The native v4 Rally
entry is a championship menu hub. Entering a stage or loading its terrain
does not establish a save-safe open-world destination and return path.

## Owned data contract

The verified Rally package's `1600000_merge.slt` contains one `Tracks` row
with `MediaName=ColoradoDirt`, `DevName=DirtFreeRoam` and `RouteId=0` (ID
1112 in the accepted package). Use its complete descriptor, including its
environment and route settings; changing only the base track's media name
leaves Colorado's other settings in place. The base free-roam track is 317.
The DLC merge tables have the same column names/types as the disc tables,
but omit their primary-key constraints. That difference is expected.

The package includes `ColoradoDirt.nav` and `Ribbon_00/TrackRoute000.xml`.
Their presence is not traffic, minimap, navigation or collectible
qualification. No new collectibles or Colorado activity locations are
invented or transplanted into this map.

The owned route 001's `start_location_00` supplies a ground-level position
and facing. Derive placement from that transform, rather than a saved
Colorado position. A forced `CPlaceCar` at every start is useful for initial
terrain tests, but **invalidates a save/resume test**.

Read-only generated-code inspection also identifies the ordinary free-roam
parameter constructors: base `sub_825558A0`, v4 `sub_825D4500`. Both select
track 317 and pass it to their respective setup functions,
`sub_82554598` / `sub_825D3548`. This does not establish that reinitializing
live load parameters is safe; no such runtime modification is implemented.

## Reference boundary

The community [Rally Freeroam Unlocker description](https://www.moddb.com/mods/forza-horizon-udlc-pack/downloads/fh1-rally-freeroam-unlocker)
says it exposes the Rally map and requires Fast Travel Anywhere. Its archive
was unavailable through automated access on 2026-10-18 (HTTP 403). Its actual
file/settings changes have therefore **not** been inspected. No files from
that pack are an input to the probe or included in this repository.

## Reproduce the initial-placement probe

`tools/create-rally-freeroam-seed.py` reads a pinned **base-disc** save and an
enabled Rally import, verifies both the disc inputs and the complete owned
payload/header through the existing DLC verifier, and publishes a new private
seed atomically. It refuses existing outputs, outputs inside input trees or
the installed AppData state, changed pinned profiles and v4 seeds. It creates
a dedicated `user-rally-probe` profile from the pinned save; it does not use
the live save or another mod's profile.

```powershell
python tools/create-rally-freeroam-seed.py `
  --seed <pinned-base-seed> --dlc-state <verified-import-state> `
  --output <new-private-seed>
python tools/run-fh1-render-test.py `
  config/render-tests/fh1-rally-freeroam-probe.fh1test `
  --state-root <new-private-seed> --seed-shader-storage
```

The runner makes another private copy. The probe changes only that mod's
database and free-roam placement flow, using assets from the verified DLC.
Its receipt explicitly lists the outstanding gates. Its `rally-map-closed`
capture returns from the map screen to Rally driving, **not to Colorado**.
The probe is not installed as a built-in mod and cannot be enabled in normal
play by a release update.

## Initial probe receipt, 2026-10-18

On multivac (Ryzen 7 5800X, Windows, Vulkan), the adaptive probe reaches
native game mode 17, moves more than 30 metres, opens the map and returns to
Rally driving. Captures show textured road/terrain, ambient and festival
traffic, and a local-road minimap. The full map still displays Colorado's
labels and base-event markers. Their alignment, destination handling and
collectible behavior on Rally terrain are not qualified.

An earlier `fh1-map` run captured the loading screen at its fixed early
capture time and failed its simulation-cadence threshold under shared build
load. It is not a passing qualification receipt. The new probe waits for a
vehicle and actual movement; no performance result is claimed from these
shared-machine runs. Neither route tests world-aware save/resume, cross-world
travel or the 20-minute gate.

The new frozen-codegen Windows Release build at `fe0dcf1d` / SDK `3bb29938`
also reached driving, but its first Rally run crashed on a null guest read
with LR `0x82BC35B0` (crash `pscrash-v1-fc5a0d238846f8d2249f`). An identical
fresh retry and an unmodified Colorado control passed. The cause is not
established; a successful retry does not dismiss the failure. The pinned seed,
19 unmodded profile files per run, and the source/seed DLC payloads and licences
were checked unchanged. Successful short runs do not qualify sustained play.

## Remaining acceptance gates

- Independently inspect the unlocker's file/settings behavior when a local
  reference is available; retain only our analysis.
- Implement an opt-in destination and return activity through the mod system,
  gated on verified, enabled owned Rally. Preserve service/race control guards
  and the current Colorado return point.
- Persist world identity with the isolated profile and restore positions in
  the correct world. Cover an interrupted transition, missing/disabled DLC,
  failed save, a mod removed before reload, and the one-way v4 save upgrade.
- On separate base/v4 private seeds: travel in, drive for 20 wall-clock
  minutes, inspect traffic/minimap/collectibles, save, close, reload at the
  saved Rally position, then travel back to Colorado with earned progress
  intact. Compare against the option disabled.

The initial-placement probe cannot close #490, even if its short route passes.
