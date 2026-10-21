# Hidden-car qualification and recovery

The built-in `hidden_cars` database patch originally exposed 22 hidden
`IsDrivable` rows. That flag also describes traffic vehicles; it does not
promise a showroom, garage, cockpit or paint model. Issue #669 reports a
tour bus selection that leaves the garage unable to load the current car.
The patch now uses an explicit list of player-model variants instead of a
query that exposes every drivable row. Updating the built-in mod rebuilds
the generated database from the original input, removing its old traffic
listings. It does not remove any already purchased car or purchased part.
The previous patch's seven traffic-car price values are retained as legacy
metadata, even though those entries are no longer offered for purchase.

## Asset audit

Audited locally on multivac, Windows, from the supported base disc on
2026-10-18. The method was a read-only database query, ZIP central-directory
inspection and local extraction of `CarAttribs.xml`. No assets are supplied
by the patch. All 22 entries have an archive, physics definition and livery
masks. Those facts alone do not qualify them for player use.

The table gives uncompressed sizes in bytes of the named LOD0 and cockpit
`.carbin` members. Many traffic archives contain small members with these
names, so checking that a filename exists would admit the bus again.
Sizes are evidence for exclusion, not a general-purpose compatibility test.
`absent` means the expected model-named member is missing.

| ID | Model | LOD0 / cockpit bytes | Sales |
|---:|---|---:|---|
| 282 | Beetle | 14,225 / 6,913 | excluded |
| 414 | PT Cruiser | 62,640 / 7,899 | excluded |
| 1241 | Taurus SHO | 172,056 / 17,539 | excluded |
| 1340 | Prius | 233,702 / 6,821 | excluded |
| 1365 | Leaf | 11,226 / 17,539 | excluded |
| 1529 | Tour Bus | 11,226 / 17,539 | excluded; #669 |
| 1530 | RAV4 Sport | 11,226 / 17,539 | excluded |
| 1531 | A4 Avant | 10,150 / 17,435 | excluded |
| 1532 | Camry | 11,226 / 17,539 | excluded |
| 1541 | Explorer | absent / absent | excluded |
| 1542 | F-350 Super Duty | 1,232 / absent | excluded |
| 1543 | Focus ZX4 | absent / absent | excluded |
| 1546 | Corolla DX | 11,226 / 17,539 | excluded |
| 1549 | Express cargo van | 11,226 / 17,539 | excluded |
| 1550 | Durango | 11,226 / 16,545 | excluded |
| 1560 | Yukon XL | 11,226 / 17,539 | excluded |
| 1561 | XC70 | 11,226 / 17,539 | excluded |
| 1562 | T440 | 11,154 / 17,539 | excluded |
| 1565 | Intro Corrado | 6,110,707 / 1,972,551 | retained |
| 1566 | Showcase Mini | 2,956,951 / 1,797,829 | retained |
| 1567 | Showcase 500 Abarth | 7,698,564 / 2,396,022 | retained |
| 1568 | Showcase 205 T16 | 4,331,822 / 2,084,678 | retained |

The placeholder 1215 remains hidden. The earlier base-build bus drive and
T440 race established driving only. They did not establish garage changes
or paint support. The four retained variants pass this asset audit;
complete garage/paint qualification is still pending. Do not reintroduce a
traffic entry without a private
profile test of purchase, thumbnail creation, garage entry and exit,
changing away and back, paint, driving and a saved reload. A v4 run is a
separate qualification. Independently authored compatibility metadata can
reopen an excluded entry once it passes those checks using the player's
own assets.

## Base Windows runtime checks

All four retained variants were bought through the native Autoshow,
created `Thumbnail_8.xdc`, saved as garage instance 8 with the expected
model ID, and loaded again. A private recommendation/one-credit price
helper made the purchases repeatable on the seven-car fixture. Removing
that helper before fresh loading tested the shipping `hidden_cars` patch,
without its class or price overrides.

Each new thumbnail also decoded to a 768x288 image with the expected car,
without the old striped-card corruption. On these four base saves, raw
DEFLATE begins at byte 20 of `cxds`: the word at byte 16 repeats the
884,788-byte uncompressed size. Inflating with window bits -15 and passing
the resulting `.xds` through the existing `hostui::DecodeXds` decoder
allowed visual review of the saved pixels, beyond the compression-ratio
heuristic.

Each fresh-load route drove the selected car in free roam for eight
seconds and passed the runner's graphics diagnostics. The three showcase
cars also rendered cockpit, hood, bumper and both chase views. The intro
Corrado's first drive did not include the camera cycle. The repeatable
view route is
`config/render-tests/fh1-hidden-car-views.fh1test`; its captures and native
saved model IDs need review as well as its exit status.

The Mini, Abarth and 205 purchase routes passed. The intro Corrado purchase
completed and saved, but that run also logged an indirect GPU ring-buffer
packet error; it began with the unsupported bus selected, so the error is
not attributed to the newly purchased model. Its separate fresh-load drive
passed. A separate base route fast-traveled to Dak's Garage with the intro
Corrado, rendered its full car view and opened the responsive garage car
selector. Native Get In Car then changed from garage ID 8 to the owned
Mustang at ID 2; decrypted load/save snapshots kept the credit balance.
The repeatable entry route is
`config/render-tests/fh1-hidden-car-garage.fh1test`; its map input is
calibrated for the pinned native purchase fixture at Gauntlet.
Garage entry for the three showcase variants, complete changes away and
back for all four, paint-shop editing and v4 qualification remain pending.
Showroom color selection alone does not qualify the paint shop.

The intro Corrado also reached the paint shop and Design Creator with its
body rendered. The initial isolated-batch run failed the graphics gate with
resolve destination-format conversions and EDRAM mode 6 draw failures.
After integration with the livery resolve corrections, the same pinned
entry route passed the graphics gate on Windows/RTX 4080, with the Corrado
body and Design Creator menu visible. This does not isolate which correction
removed the earlier errors. Editing, saving and reloading this car's paint
remain unqualified. The purchase run's indirect-ring-buffer error is separate.
`config/render-tests/fh1-hidden-car-paint-entry.fh1test` reproduces the
entry path and stops before changing paint.

The pinned bus-selected base fixture also fast-traveled to Dak's Garage
and displayed the bus in its garage view. Its large body clipped the
garage camera. Native car selection changed away to the owned Lancer and
Audi (garage IDs 7 to 3 to 5), preserving credits. The reported loading
block was not reproduced by those paths on this Windows configuration.
The attempted return-selection route picked different cars, so selecting
the bus again, painting, v4 and the reporter's GPU remain separate checks;
the report has no diagnostic attachment or title version.

## Recover an existing modded selection

Close the game. From the install's source folder, run:

```powershell
python tools/fh1-profile.py recover-car --state-root "<state>"
```

For an installed Windows preview, `<state>` is
`%LOCALAPPDATA%\PinyonShift\source\<version>\.local\preview`, the folder
holding `config` and `user-modded`. Use the same title version that last
saved the profile: v4 saves require v4.

The command copies the selected XUID's entire `user-modded` profile and the
settings into a new `backups/before-car-recovery-<time>-<id>` directory, with
a SHA-256 manifest. Only after the copy is verified does it queue
`Main/CareerCar=0` through the one-time `cheat_set_profile_fields` load hook.
This exact request uses the isolated profile with the trainer off, so
dormant credit, speed or other cheat settings stay disabled. The trainer
setting is preserved. No encrypted file is edited. A missing
modded profile, an existing pending field edit or a mod with its own named
profile stops the operation without changing settings. It never writes
`user` or shared DLC installations.

Keep a save-isolating mod such as `hidden_cars` enabled to continue that
profile after the one-time request clears. Start the game, let it finish
loading and saving, then restart. Zero is an
invalid garage ID; the title's missing-car path supplies a starter Corrado.
On the pinned seven-car bus save, the base build added that fallback as
garage ID 8 and returned to free roam. Decrypted load/save snapshots kept
all seven original garage rows, all 122 original purchased-part rows and
67,700 credits; the fallback added 20 part rows of its own. Recovery
does not sell the bus,
refund it or remove its parts; avoid selecting the unsupported car again.
The request clears after it is applied. A fresh reload with no pending
request reached free roam and car select with that Corrado on the private
Windows Release build. The unmodded tree's 19 file hashes still matched
the pinned seed. Integration repeated trainer-off backup, recovery, save and
reload on the Windows base and v4 builds using separate private fixture
copies (the title upgraded the v4 copy). Both retained the original cars,
parts and credits, verified all 20 backup entries and preserved dormant
cheat flags and the 19 unmodded hashes. This qualifies recovery on that
fixture, not every hidden model or the reporter's loading block. Continue using the modded profile
(keep a save-isolating mod or the trainer enabled); disabling all of them
returns to the separate unmodded save.

To cancel before starting, restore the backed-up `config/pinyon_shift.toml`.
To undo after playing, close the game, retain another copy of the current
selected `user-modded/<XUID>` directory, then restore that directory and the
settings from the recovery backup. Restore the whole profile directory,
including `PlayerDatabase`, `VersionFlags`, liveries and thumbnails, with
the same XUID and title version. Never restore only `ForzaProfile`.
