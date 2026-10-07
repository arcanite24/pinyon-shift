# DLC support backlog

Status: **open**, inventoried 2026-10-04. Priority follows gameplay breadth:
Rally, 1000 Club, monthly car packs, VIP, Honda, pre-order and exclusive cars,
then LCE paint variants. Implementation starts with the shared import and
base-disc prerequisites, even when a small car pack is the first test case.
The public checklist lives in the [README](../README.md#dlc-support-priorities).

## Immediate priority: the original Rally experience

User direction, 2026-10-05: restoring the original playable Rally experience
is the highest priority, ahead of the graphics and low-spec work recorded in
[LOW_SPEC_BACKLOG.md](LOW_SPEC_BACKLOG.md#requested-defaults-and-feature-trades).
The F6 settings-menu championship launcher is a development shortcut and does
not satisfy the player-facing entry requirement.

- [ ] Restore the expansion's original discovery, map markers, physical event
  activation and Rally menus on the supported base disc, with owned-content
  gating and the original intro/loading flow. Verify the intended sequence
  against the owned reference data without requiring the supplied v4 update.
- [ ] Connect that entry to car selection, all seven championships and their
  four stages, authored routes, checkpoints, co-driver calls, timing and results.
  Qualify manual driving; diagnostic AI finishes are insufficient.
- [ ] Restore the original scoring, rewards, XP/wristbands, unlocks, stage
  transitions, retirement and return to free roam. Preserve and resume earned
  progress across fresh launches through the normal Rally flow.
- [ ] Complete a manual end-to-end acceptance run starting in free roam,
  discovering and entering Rally through its intended game flow, finishing a
  championship, receiving its rewards, reloading and continuing. Do not require
  F6, render-test commands or diagnostic driving to complete this run.

**Done when:** the player can discover, enter, drive and progress Rally as in
the original offline experience. Existing F6, asset, audio and persistence
receipts remain useful subsystem checks; they do not close this requirement.

**2026-10-06 update:** v4 applies byte-exactly to the supported `2DC7007B`
disc. Every page of all three modules verifies against v4's own hashes. The
original Rally and 1000 Club behaviours exist only in v4's code. These
criteria are now pursued through the native v4 build in the
[title update v4 backlog](TITLE_UPDATE_V4_BACKLOG.md) (TU-6). The "without
requiring the supplied v4 update" wording above predates that finding. The
base-disc build remains the default until the v4 build qualifies.

## Goal and current support

Load the player's own FH1 DLC through the title's content system, make its
offline gameplay usable, and retain progress across restarts. Keep the base
disc as the DLC target without relying on v4 (user direction, 2026-10-04).
An optional updated build is separate work. That direction assumed v4 could
not run on this disc; see the 2026-10-06 update above and the
[title update v4 backlog](TITLE_UPDATE_V4_BACKLOG.md). No game content, generated
translations or DLC binaries are distributed with the project.

Vulkan is the sole supported graphics API (user direction, 2026-10-05).
Direct3D 12 is legacy and unsupported. All new DLC and Rally qualification
targets Vulkan; existing Direct3D 12 receipts below remain historical evidence.

Treasure Map functionality is already implemented in
`src/dlc_treasure_map.cpp`; it is an in-game consumable restoration, not proof
that Marketplace packages work. Every package below remains **unqualified**.
Online recognition, leaderboards and service-backed features must be assessed
separately from local cars, events and progress.

## Local inventory

The local `Forza Horizon.zip` contains 21 distinct package filenames under
`4D5309C9/00000002`. Their STFS headers identify FH1 Marketplace content.
Adjacent add-on files contain raw `LIVE` packages or ZIP-wrapped packages,
despite having no file extensions. This inventory establishes availability and
package identity. The pinned [catalog](../config/supported-dlc.json) records
21 identities, 30 accepted whole-package hashes, extracted file counts and
payload hashes. Gameplay qualification is pending.
It does not establish that every historical DLC variant has been collected.

| Priority | Content | Packages observed | Inventory note |
| --- | --- | ---: | --- |
| P1 | Rally Expansion Pack | 1 | Raw package inside both the aggregate and an adjacent ZIP wrapper |
| P1 | 1000 Club Expansion Pack | 1 | Aggregate and adjacent raw package |
| P2 | October Car Pack | 1 | Aggregate and adjacent ZIP wrapper |
| P2 | November Bondurant Car Pack | 1 | Aggregate and adjacent raw package |
| P2 | December IGN Car Pack | 1 identity | Aggregate, adjacent raw package, and a differently labelled wrapper; reconcile variants |
| P2 | January Recaro Car Pack | 1 | Aggregate and adjacent raw package |
| P2 | February Jalopnik Car Pack | 1 | Aggregate and adjacent raw package |
| P2 | March Meguiar's Car Pack | 1 | Present in the aggregate archive |
| P2 | April TopGear Car Pack | 1 | Adjacent file is labelled simply "TopGear Car Pack" |
| P3 | VIP Membership & Cars Pack | 2 | Same display name, distinct package filenames and sizes; inspect both |
| P3 | Honda Challenge Car Pack | 1 | Aggregate and adjacent raw package |
| P4 | Pre-Order Car Pack | 1 | Qualify the bundle before overlapping individual entitlements |
| P4 | Season Pass: 2006 Lamborghini Miura Concept | 1 | Present in the aggregate archive |
| P4 | 2013 Ford Shelby GT500 - Rockstar Energy | 1 | Present in the aggregate archive |
| P4 | 2010 Nissan 370Z; 2010 Ferrari 458 Italia; 2011 Mercedes-Benz SLS AMG; 2010 Volkswagen Golf R; 2012 Aston Martin Virage | 5 | Individual promotional packages in the aggregate archive |
| P5 | LCE: Day1 DLC Pack | 1 | Aggregate folder calls it "October Car Pack + 5 custom painted LCE Cars" |

The adjacent file labelled **2006 Ford GTX1** is a ZIP containing package
`BC6F8A24F1F38F719B9F09C002DDC1F3024AC2AB4D`, whose header says **December IGN
Car Pack**. Its payload SHA-256 differs from the adjacent December IGN raw
package, despite matching name, package filename and size. All three December
variants extract to the same 24 files with identical SHA-256 values. They are
accepted as alternate inputs; original licence masks are preserved. Importing
a different variant over an existing installation reports a conflict.

The two VIP package filenames are
`210BB00587D95ACFD8CEDCA23B7E16AE2C59C3DB4D` and
`A5B171B88811F1785A9AFC1F956C768A97029C004D`. Determine their roles and overlap
from their contents; the identical display name is insufficient to deduplicate.
The larger package supplies offer `2100` and 10 files; the smaller supplies
offer `1006` and 8 files. Both contain Gallardo/GT3 RS engine audio, but their
archives and offer data differ. Keep both identities separate pending gameplay tests.

The standalone Rally wrapper is **rejected**: its `ColoradoDirt_pri_65.zip`
differs from the aggregate variant in 48,980 bytes, and three changed terrain
members fail XMem decompression. The same members in the aggregate variant
decompress successfully and match their archived CRCs. Use the Rally package
inside `Forza Horizon.zip`; its accepted hash is pinned in the catalog.

## Implementation checklist

### DLC-0: verify inputs and the base-disc foundation — P0

- [x] Catalog raw and wrapped packages using their headers and contents, not
  outer filenames: title ID, content type, package filename, display name,
  size, SHA-256 and member list. Reconcile the December/GTX1 and VIP cases.
- [x] Pin accepted local input hashes without committing binaries or extracted
  assets. Reject wrong-title, corrupt or conflicting inputs with a useful reason.
- [ ] Qualify DLC on the supported `2DC7007B` base build. Port missing behavior
  or asset handling directly; do not make the supplied v4 a prerequisite.
- [ ] Validate title screen, opening drive, free roam, a race, save/reload and
  exit with enabled DLC on the base build.

**Done when:** the inventory is unambiguous and the base build passes baseline
routes with enabled DLC, without changing source inputs or live saves.

#### Separate optional v4 work (not a DLC dependency)

Superseded 2026-10-06 by the [title update v4 backlog](TITLE_UPDATE_V4_BACKLOG.md),
which now owns these items.

- [x] Obtain and verify a compatible base for the supplied v4 package. The
  package targets media `4000D145`, source version `0.0.0.12`; the currently
  supported disc is `2DC7007B`, version `0.0.0.10`. The signatures differ only
  because the headers differ. The facade key failures were caused by the SDK
  truncating multi-record header deltas. All three patches apply to this disc
  and verify page for page (TU-0).
- [ ] Build v4 into separate game, generated-code and build directories. Port
  and verify hooks, runtime constants, facade translations, mod symbols and
  shader inputs against that exact executable set; mount its update media.
- [ ] Validate title screen, opening drive, free roam, a race, save/reload and
  exit on the updated build, while retaining a working base-disc launch.

Reuse [the title-update verifier](../tools/verify-fh1-title-update.py) and
[the pinned update manifest](../config/supported-title-updates.json).
The verifier checks inputs; it does not make the native v4 port playable.
Record each DLC's actual update dependency during qualification rather than
assuming the supplied v4 works with every base dump.

### DLC-1: import, enumerate and mount owned packages — P0

- [x] Reuse the SDK STFS reader and content header writer.
  `ContentManager::InstallContent` in
  `thirdparty/shiftglue-sdk/src/system/xam/content_manager.cpp`. Audit destination
  containment and incomplete-import cleanup before exposing it to player input.
  That function accepts short reads and can publish partial content. The existing
  project extractor checks paths and full reads, preserves the licence mask,
  and uses `ContentManager::WriteContentHeaderFile` for SDK-compatible headers.
- [x] Accept a raw package, a folder or a ZIP containing packages. Validate
  archive paths and the inner packages, import atomically, detect duplicates
  and report conflicting variants. Leave original files untouched.
- [ ] Trace FH1 Marketplace enumeration, content creation and licence queries
  through the SDK; verify the `DLCRoot<n>` mounts and `media/<offer>.puboffer`
  handling described by `content.mount_marketplace` in
  `config/mod/fh1-symbols.toml` on the supported base build.
- [x] Provide launcher import, detection, enable/disable, missing-content and
  conflict reporting in its existing state root. Imports start disabled;
  gameplay qualification remains pending.
  Enabling Rally now verifies ownership and the base-disc inputs and prepares
  its assets. The panel distinguishes cached assets from unverified gameplay;
  a preparation failure leaves the package recoverable and does not touch saves.
- [ ] Honor entitlement for successfully imported player-provided packages.
  Show detected content, unsupported requirements and failures in the launcher.
  Reuse its current install/state roots; avoid a second DLC storage system.
  Rally's native entitlement cache now matches its imported licence mask:
  the main offer is owned and the season-pass Focus SVT is excluded. Other
  packages remain unqualified. One owned Escort purchase and fresh reload now
  pass on Vulkan with the complete saved garage; see the dated receipt below.
- [ ] Use one small representative car pack to verify enumeration, database
  merge, car purchase, garage rendering, driving, upgrades and save/reload.
- [ ] Check repeated import, wrong-title packages, interrupted import, missing
  packages on restart, and safe disable/uninstall with a DLC car in a test save.
  A saved base-car Rally tyre now gives a recoverable stop when Rally is disabled,
  retaining all profile files. Re-enable/reload passes for the Mustang. Stock
  Escort disable, base-car save and restoration also pass with the complete
  seven-car garage retained. Other DLC cars, upgraded missing cars and uninstall
  remain unqualified.

**Done when:** one package is usable through the normal title flow, repeated
imports are stable, and a missing package gives a recoverable result without
losing profile data. Package mounting alone does not count as DLC support.

### DLC-2: Horizon Rally — P1

Depends on DLC-0 and DLC-1.

The base build has enumerated the verified Rally package and successfully
opened `DLCRoot0`. This establishes mounting, not playable Rally.
The package's database supplies the `ColoradoDirt` environment and 34 track
records. Its seven event activation locations refer to Rally events that the
base flow does not implement. Inspection of the base mapped image found no
Rally-specific strings; the update reference adds scoring, wristband/XP,
multi-stage progression and Rally flow behavior. Implement those missing
systems on the base build; importing or overlaying assets alone is insufficient.

- [ ] Mount and merge the expansion's assets, database, events and upgrade data.
  Shared owned-asset preparation is verified against the actual accepted package:
  all 28 new stage mappings, 682 authored calls and 2,011 samples are cached,
  with the base event/race preserved. Preparation also generates seven owned
  entry locations, stage transitions and localized event names while preserving
  existing base activities. Normal launch preflight and base-world/map loading
  are verified; activity activation and full database/upgrade qualification
  remain open.
  The normal title merge also supplies all 16 car rows with matching tyre,
  suspension and engine option counts. This verifies database contents,
  not usable upgrade parts or every car's physics. The owned Escort now passes
  normal purchase, fresh reload and basic free-roam driving.
- [ ] Enable the Rally entry flow and qualify intro/loading transitions,
  routes, checkpoints, timing, results, progression and return to free roam.
  Host-menu entry now checks native game-control ownership, including the
  separate pause owner used by F6. A private Vulkan run blocks selection in
  Dak's Garage, restores availability on exit and resumes the saved stage.
  Other garage/service/cutscene contexts and full entry flows remain to qualify.
- [ ] Verify Rally cars and upgrade parts, terrain rendering, dust, audio and
  pace notes in English plus at least one other supported language.
- [ ] Port and qualify Rally tyre, suspension and transmission conversions for
  base-disc cars. The package supplies parts for its own 16 car rows; preparation
  recipe 7 retains tyre conversions for 173 base-car entries and grounds finish
  camera targets against native terrain. An owned Mustang's
  native tyre purchase, save/reload and initial Rally driving pass. Base-car
  suspension/transmission conversions remain to port; shared menu definitions
  alone do not supply their missing physics and part data.
  Verify a base car's normal purchase, tuning, driving and save/reload without
  changing entitlement or replacing its stock parts.
- [ ] Complete an event, save/reload its progress and run a sustained route on
  Vulkan. Keep simulation and timing correct above 30 fps.

**Done when:** Rally can be entered, driven and progressed locally across
restarts, with its cars and upgrades usable and no regression in the base routes.

### DLC-3: 1000 Club — P1

Depends on DLC-0 and DLC-1; assess Rally-dependent challenges separately.

- [ ] Trace challenge discovery, menu activation and any live-service gates.
  Establish which challenges can run locally before promising offline support.
- [ ] Load the challenge data and expansion cars; verify challenge selection,
  completion, medal notifications, per-car totals and profile persistence.
- [ ] Qualify representative driving, speed, skill and event challenges, plus
  challenges involving other installed DLC. Explain unavailable prerequisites.
- [ ] Assess local achievement tracking separately from service-backed
  comparisons or leaderboards; handle unavailable services without hangs.

**Done when:** the documented local challenge subset works and keeps medals
after save/reload. Record any unavailable service features in the README.

### DLC-4: monthly car packs — P2

Depends on DLC-1 and each pack's verified update requirement.

Qualified on the v4 build with all 21 owned packages enabled together (see
"Car packs on v4" below): every pack's roster is installed, purchased and
visible in the native entitlement cache, and one representative car per pack
was bought in the Autoshow, reloaded from a fresh launch and driven.

- [x] October Car Pack (Gumpert Apollo Enraged)
- [x] November Bondurant Car Pack (Shelby Cobra 427 S/C). The full pack needs
  the full-licence variant; the importer now combines owned variants.
- [x] December IGN Car Pack (AMC Javelin AMX); all three local variants are
  accepted and their licences combine.
- [x] January Recaro Car Pack (GMC Vandura G-1500)
- [x] February Jalopnik Car Pack (Devon GTX)
- [x] March Meguiar's Car Pack (Joss JT1)
- [x] April TopGear Car Pack (Bowler Nemesis EXR)

For each pack, establish its expected car roster from its own database/assets.
Verify every car is visible, purchasable, rendered correctly in the garage and
on track, and retained after restart. Exercise tuning/upgrades on a representative
car, then run all seven packs together to catch database or asset collisions.

**Done when:** each pack passes that matrix individually and in combination.
Mark its README checkbox independently.

### DLC-5: VIP, Honda and exclusive cars — P3/P4

Depends on DLC-1 and each package's verified update requirement.

- [x] VIP: both packages mount; the five VIP cars are owned and the Koenigsegg
  Agera was bought, reloaded and driven on v4. v4's VIP perk Fast Travel
  Anywhere is granted by `pinyon_shift_dlc_fast_travel_anywhere` (DLC-7);
  online VIP recognition is a removed service.
- [x] Honda Challenge: the three Honda cars are owned; the 1986 Civic Si was
  bought, reloaded and driven on v4. The named Honda challenge flow itself
  has not been qualified.
- [x] Pre-Order bundle: its five cars are owned (the five single-car packages
  carry only wheels and strings for the same cars, so they overlap without
  duplicates); the Nissan 370Z was bought, reloaded and driven on v4.
- [x] Season Pass Miura Concept and Rockstar Energy Shelby GT500: both bought,
  reloaded and driven on v4 with test credits (2026-10-07). Original text: qualify
  assets, entitlement, purchase and persistence without requiring an online store.
- [ ] Nissan 370Z, Ferrari 458 Italia, Mercedes-Benz SLS AMG, Volkswagen Golf R
  and Aston Martin Virage: verify each individual entitlement and bundle overlap.

**Done when:** the car-pack matrix passes without duplicate cars, lost purchases
or unsupported membership promises. Verify local perks through observed behavior.

### DLC-6: LCE paint variants and combined qualification — P5

- [ ] Inspect LCE: Day1 DLC Pack against the normal October pack; qualify its
  distinct cars/paint variants, thumbnails, garage rendering and save persistence.
- [ ] Run the complete supported package set together: base routes, Rally,
  1000 Club, garage, upgrades and save/reload. Recheck duplicate entitlements.
- [ ] Verify disable/re-enable behavior with DLC purchases and medals in a
  private profile; provide clear missing-content guidance without resetting it.
- [ ] Update the README from recorded results, listing any platform, language
  or service limitations beside the relevant item.

**Done when:** LCE variants coexist with the ordinary packs and the full
qualified content set survives normal play and restart without data loss.

### DLC-7: token-store unlocks and the Token balance — P2

Like the Treasure Map (`src/dlc_treasure_map.cpp`), these were sold in the
in-game marketplace for Tokens counted by Turn 10's web service
(`ForzaUserGetForzaAssetCounts`, `ForzaUserTwoPhaseConsumeForzaAsset`), not
as Marketplace content packages, so they do not depend on DLC-1.

- [x] Fast travel anywhere (v4 only; the base disc has no such unlock). The
  purchase completion, sub_825D5C00, stores the profile value
  `Main/FastTravelAnywhere = true`; `pinyon_shift_dlc_fast_travel_anywhere`
  (default on) stores it the same way once per loaded profile in free roam.
  The map's Y then fast travels to any road, and a fresh launch with the
  setting off keeps it (2026-10-07, commit `fa19331`).
- [ ] Token amount: trace where the title stores the asset count returned by
  `ForzaUserGetForzaAssetCounts` and how purchases consume it, then let the
  player set the balance (setting or cheat). Verify the showroom's
  "or N Tokens" prices, a token car purchase, a token-store unlock and the
  balance after save/reload, without the removed web service.

**Done when:** both work offline on Vulkan from a pinned seed, survive
restart, and turning the options off never removes what was already granted
or bought.

## Validation and completion rules

Qualify supported gameplay and save/reload on Vulkan. Direct3D 12 runs are
historical or optional developer diagnostics and are not completion gates.

Use [create-render-seed.py](../tools/create-render-seed.py) to take a read-only
snapshot, then run routes through
[run-fh1-render-test.py](../tools/run-fh1-render-test.py) in its private per-run
state. Neither scripted gameplay nor DLC import experiments may write to the
AppData save or overwrite a pinned seed. Keep expansion progress seeds separate
from base seeds, with the update and installed-package hashes recorded.

For every completed item record the source/build revision, exact base/update
and package hashes, graphics backend, language, routes, result and limitations.
Test normal failure/recovery as well as the happy path. Keep binaries, raw
traces, screenshots and private profiles under ignored local paths. A package
is checked off only after playable content and persistence pass, not merely
because a dump exists or its container can be opened.

### Foundation evidence — 2026-10-04

- Imported all 21 catalog identities into a private state, starting disabled;
  verified extracted payloads and SDK entitlement headers. Repeated imports,
  extraction failure/retry, wrong-title inputs, changed hashes, ZIP traversal,
  missing headers and damaged-payload repair have regression coverage. Repair
  retains the previous payload in the state's `dlc/replaced` directory.
- Launcher layout and management states pass at 940×640 and 1080×720 with 21
  rows. Enable/disable accessible names include the package name. Import and
  launch/relocation controls cannot race in the DLC panel.
- `fh1-map.fh1test` passes with the accepted Rally package mounted on the
  `2DC7007B` base build, separately on Vulkan and Direct3D 12. These are newly
  recorded baseline captures, not Rally event qualification. Direct3D 12 needs
  the prepared native shader pack as well as its seeded catalogs.
- Save snapshots exclude Marketplace assets and headers. Restoring a save
  preserves the current enabled/disabled installation, including deep Windows
  asset paths and legacy backups containing DLC. Private render state copies
  support those paths too. Live saves and original inputs remain untouched.
- Modded profiles use the launcher's shared Marketplace root and keep their
  save root separate. The SDK root-selection change must be included in the
  pinned SDK revision before packaging a release.
  The host content-root test writes and enumerates real SDK headers, verifies
  shared DLC visibility from a second profile, checks save headers remain in
  the modded profile, and checks an unset/reset override preserves SDK defaults.
- A private asset-only mod, built from the base database and verified Rally
  package without any update media, switches the free-roam track to
  `ColoradoDirt`. This exposed an overlay parent-directory bug: new asset
  files could resolve but not open because their parent was absent on disc.
  Directory fallback now exposes new overlay directories while preserving
  existing base directories, with a VFS open/read regression test.
  The experiment passes the Vulkan free-roam/map/return script, but visual
  inspection shows missing or untextured ground surfaces. Terrain rendering
  therefore remains unqualified; a script pass does not establish full asset
  coverage. The experiment is private and does not enable Rally in normal play.

### Base-disc Rally investigation — 2026-10-04

- A private base-plus-Rally experiment now places the car at Rally route 001's
  start (`-4820.71, 36.15, -2617.82`). Vulkan and Direct3D 12 captures show
  textured road and surrounding terrain, and movement with stable ground
  collision. The
  `fh1-map.fh1test` run passes, including map entry and return. This validates
  one starting area, not all routes, assets or rendering effects.
- The experiment uses a copied base database, Rally's own assets and the base
  game-flow behavior `CPlaceCar`. It does not load v4 code or media. A normal
  saved Colorado position is unsuitable as a Rally spawn: the earlier test
  fell through the ground there. Production Rally entry must select a valid
  route position rather than reuse that save position.
- Packed game-flow members take precedence over loose XML. Repacking must
  update central extra field `0x1123`, an absolute payload offset used by the
  guest reader. The new archive patch tool preserves opaque XMem members and
  updates those offsets. Its output matches the successfully tested private
  flow archive byte-for-byte; offset preservation and original-file protection
  have regression coverage.
- A smaller experiment without startup terrain replacements passes on Vulkan
  and Direct3D 12, using the new archive tool's output. Direct3D 12 uses the
  prepared native shader pack and seeded catalogs. An earlier Vulkan run
  reports a GPU indirect-ringbuffer failure; later runs pass, but the cause
  has not been established. Keep that failure in further route qualification.
- October imports and enables with the original license mask. The base event
  purchase route still selects a base Jaguar; this is not October car purchase
  qualification. A private Autoshow trigger overlaps the existing event and
  therefore has not established the pack's full car roster in the UI.
- Windows modded-profile publication now retries a briefly denied directory
  rename, retaining atomic publication. A regression test holds a directory
  handle without delete sharing, releases it and verifies the complete copied
  profile becomes available. Permanent errors still fail without publishing.

### Base-disc solo stage probe — 2026-10-04

- Rally route 001 starts through the base race engine, with a running race
  clock, driving physics, collision, racing line and textured terrain. A new
  solo event and track record preserve the original Gauntlet database rows.
  A generic entry activity launches the new event directly. No v4 input is
  needed. The packaged seed builder and stage-start scenario pass on Vulkan
  and Direct3D 12, including race HUD checks and movement captures.
- The normal DLC database merge restores Rally's `RibbonConfiguration=8`.
  The base engine then shows a lap counter. A separate track record with
  the base sprint flags survives that merge and shows the progress HUD.
  Generic portals belong in `Colorado/activities.xml`; attempts to put an
  unknown event or generic portal in the career activation file did not enter
  the stage. Direct event loading through the generic activity succeeds.
- This is a private diagnostic route. It borrows the Media Center prompt,
  base event labels and base race flow. Its portal suppresses the nearby
  Gauntlet trigger in the copied seed. It establishes entry and the first
  metres of one solo stage, not official Rally progression or completion.

Create a new seed from the pinned save and an accepted Rally installation:

```powershell
python tools/create-rally-stage-seed.py --seed .local/render-seeds/appdata-2026-09-27 --dlc-state .local/dlc/import-test --output .local/render-seeds/rally-stage-001
python tools/run-fh1-render-test.py config/render-tests/fh1-rally-stage-start.fh1test --state-root .local/render-seeds/rally-stage-001 --output .local/dlc/rally-stage-vulkan --record-baseline --hidden --timeout 180
```

The builder verifies the pinned profile and installed Rally payload, accepts
an enabled or disabled verified import, and refuses existing output or an
output inside any input directory or the AppData save. `--route 1..21` or
`--route 41..47` selects
a different stage for research; only route 001's starting area is qualified
by these probes. The runner makes a separate private copy for every run.
The older Direct3D 12 receipts used native shader-pack and cache options;
new qualification runs use Vulkan.
Add `--autopilot` when creating a new seed to let the base game AI drive the
stage through its normal physics and route tracking. The longer
`config/render-tests/fh1-rally-stage-ai.fh1test` scenario captures route progress,
the finish and the return after continuing through the base results UI.
The first Vulkan run reaches 10%, 59%, 89% and the **Finished — 1st Place**
screen on route 001. The D3D12 run also reaches that finish screen, continues
through results and returns to free roam. Its private saved profile records
20 races, up from 19, and the base race bonus. A fresh private restart on
Vulkan reloads those values and passes free roam, map and return with stable
ground collision. These are base career statistics; official Rally scoring
and saved progression are still absent. The AI uses normal driving physics
and no teleports during the stage.

Gameplay acceptance remains open: representative DLC car purchase and
persistence, safe disable with a purchased DLC car, production Rally entry,
full stages, timing/results, upgrades, pace notes and saved progression.
The native result fields and retirement return have since been qualified
below. Retry, official multi-stage scoring and series progression remain open.
Keep the diagnostic adapter private until full gameplay and save/reload pass.

### Native stage timing and launcher recovery — 2026-10-04

The optional `PINYON_SHIFT_RALLY_TRACE=1` observer reads the player selected by
the base game's `CWaitForEndCondition` (`sub_82982870`) and its race statistics
record (`sub_8262B348`). On a private Vulkan route 001 run, the record's double
at offset 72 advances with the race HUD and freezes at 171.188133 seconds when
the car's end flag at offset 14603 becomes 1. The statistics end reason at
offset 168 becomes 1, and offset 88 holds the same final time. The global
race manager's time keeps advancing after the finish; it must not be used as
the stage result. The AI scenario's `expect-race-finish` assertion now requires
the native player end condition, success reason and stable finite final time.
It enables the observer only in the child test process. The recorded finish
passes that assertion; ongoing/retired traces and changing final times fail
its regression checks. The observer does not write guest state or save Rally
progress.

The private retirement scenario selects **Quit Race**, confirms retirement
and returns to Colorado. Its trace never reports a completed stage. The first
run stopped during return loading; the extended run's final capture shows
stable Colorado free roam. An incidental loading-frame capture made the
extended script fail its image check. Those transient captures have been
removed, and the revised retirement script passes on Vulkan with the final
capture showing Colorado free roam. Its trace fails the new finish assertion,
as an unfinished stage should. Retry and progress cancellation across that
load remain open.

The launcher now lists other packages when an import record is damaged.
Enabled content can be disabled even with a damaged record or missing header;
enabling still requires the accepted package and verified header/payload.
Reimporting the original package repairs an unreadable record. Python import
regressions and the WPF management/layout checks pass; all 21 private catalog
imports still report gameplay unverified.

### Native stage persistence — 2026-10-05

The private adapter now writes `rally-progress.toml` beside the active
`ForzaProfile` save. It tracks completion counts and best times for routes
1–21 in its original version. The observer resolves the actual mounted profile directory, including
the isolated modded profile, rather than selecting a global user directory.
It requires the adapter's current native event ID and race mode, observes
that attempt running, then requires two stable successful finish samples.
It cancels an attempt on leaving the event and never awards a loaded finish.
Writes replace the old record atomically; failed writes can retry, while
malformed or newer records are preserved and reported.

The Vulkan route 001 run saves exactly one completion at 171.145401 seconds.
Repeated finish observations leave the count at one. A separate private
restart loads that completion and best time and passes free roam, map and
return. The progress file's SHA-256 is unchanged across that restart.
Host regressions cover retirement, event changes, duplicate results, retries,
best times, write failure and unreadable records. The stage AI scenario now
requires the matching native completion to persist to the isolated profile;
it enables the progress observer only in its child process.

The native progress observer also passes the private Vulkan retirement
scenario: **Quit Race** returns to Colorado free roam without any completion
event, progress file or progress error. Save-backup regressions confirm that
the stage record follows profile copy, backup and restore, while installed
Marketplace content stays separate.

The full D3D12 stage run passes the new persisted-result assertion, saves one
completion at 171.537537 seconds, continues through the base results UI and
returns to Rally free roam. A separate D3D12 restart loads that exact result
and passes free roam, map and return; the stage record stays byte-for-byte
unchanged. This qualifies native solo stage persistence on both renderers,
not the official Rally series systems listed below.

This is a stage-result foundation. It does not complete official Rally
series scoring, XP, wristbands, unlocks, event UI or pace notes. Those
acceptance checks remain open, and the adapter stays private behind
`PINYON_SHIFT_RALLY_PROGRESS=1`. Create a new stage seed with the current
builder so it includes the native event/route mapping; do not modify an
existing pinned seed.

### Fourth stages and save migration — 2026-10-05

The owned Rally database also includes championship routes 41–47, with
`RALLY_025` through `RALLY_031` track names. Reference event relationships
place these as the fourth stages of the seven rallies, bringing the total
to 28. Free roam, route 24, routes 100–102 and the developer test route 211
are separate and must not be counted as championship stages.

The native stage record now uses version 2 with all 28 route IDs. It reads
the earlier 21-route version without changing it, then migrates atomically
when the next stage completion is saved. Regression tests retain the old
completion and best time while adding a route 41 result; malformed and newer
records remain protected. The seed builder accepts all 28 routes using only
the supported base disc and verified owned Rally content.

Use the researched event relationships when implementing series transitions;
do not group the route IDs numerically. Routes 10 and 11 are reversed relative
to their `RALLY_010`/`RALLY_011` track names.

| Series ID | Stage route IDs, in order |
| --- | --- |
| `MS_RALLY_01` | 11, 10, 12, 44 |
| `MS_RALLY_02` | 13, 14, 15, 45 |
| `MS_RALLY_03` | 4, 5, 6, 42 |
| `MS_RALLY_04` | 19, 20, 21, 47 |
| `MS_RALLY_05` | 7, 8, 9, 43 |
| `MS_RALLY_06` | 16, 17, 18, 46 |
| `MS_RALLY_07` | 1, 2, 3, 41 |

The AI scenario now waits for the actual saved finish before continuing
through results. Longer fourth stages no longer depend on route 001's
finish schedule. This is qualification infrastructure for the full expansion;
official series entry, stage transitions, scoring and unlocks remain open.

The private Vulkan route 41 run finishes in 235.505070 seconds, saves one
completion in the 28-route record and returns to free roam. Its finish and
return captures have been reviewed. The first D3D12 run also saves a route
41 finish, but its final capture stops on the cash-reward screen: a passing
image check did not prove return. The revised scenario presses through the
remaining results and waits for native free-roam mode 17. Its return capture
must record mode 17, so a results screen in mode 3 cannot pass.

The corrected D3D12 run finishes route 41 in 237.732872 seconds, saves exactly
one completion and passes the native free-roam return assertion. Its final
capture records mode 17 and shows the stopped player car on stable Rally
terrain. Route 41's long-stage finish, persistence and return are therefore
qualified on both renderers; the remaining routes and series flow still need
their own gameplay qualification.

A separate private D3D12 restart reads the new 28-route format, loads one
route 41 completion at 237.739763 seconds and passes free roam, map and
return. The stage record is byte-for-byte unchanged across that restart.

The current reader also passes a private Vulkan restart of the earlier
21-route record: it reloads the original route 1 completion and 171.145401
second best time without a progress error or new completion. Its file hash
is unchanged. Opening an older record alone does not rewrite it.

### Base-disc stage transition probe — 2026-10-05

The private probe now maps multiple native events to owned route IDs. Mapping
version 1 remains readable; version 2 rejects duplicate event IDs, duplicate
routes, non-championship routes and future versions without changing the
metadata. The seed builder's optional `--next-route` adds a second event and
patches the completed-results branch to call the base game's
`CLoadIntoCareerRace`. Retirement keeps the original return branch, and the
transition preserves the base player-car restoration and loading preparation.
No title-update executable or media is used.

The first probe stalled because its cleanup exit targeted a missing node.
The transition assertion rejected it. The corrected graph declares that node,
and a regression check protects the link. The corrected private Vulkan and
D3D12 runs both save exactly one route 1 completion, then enter route 2 as
native event 248 with a new race serial and an advancing timer. Route 1's
saved times are 171.819449 seconds on Vulkan and 171.718065 on D3D12. Reviewed
route 2 captures show 43% progress, a working race HUD and the car travelling
at 117 km/h on rendered terrain.

Use [the transition scenario](../config/render-tests/fh1-rally-transition.fh1test)
with a new `--route 1 --next-route 2 --autopilot` seed. Its
`expect-rally-transition` assertion requires a saved first stage followed by
two advancing samples from a different native event and race serial. A
repeated first route, results screen, unsaved finish or stopped timer fails.
The test stops while route 2 is running; it does not qualify route 2's finish.

The same patched seed also passes retirement on Vulkan and D3D12. Both runs
observe route 1 running, quit before completion and capture native free-roam
mode 17 at the Colorado entry. Neither run enters event 248, awards progress,
reports a progress error or creates a stage record. The retirement scenario
now asserts this running-stage-to-free-roam sequence and rejects a finished
stage or any saved award. The pinned input profile's SHA-256 remains unchanged.

This fixed two-stage probe proves one base-disc loading handoff. Its
`--next-route` branch always selects the same next event. The separate series
director below adds stage selection and persisted attempts. Official entry UI,
scoring, XP, wristbands, unlocks and pace notes remain open. Keep the adapter
private until those requirements are qualified.

### Private four-stage director and resume — 2026-10-05

A new `--series 1..7` seed uses the researched order above and four distinct
native events. Version-3 mapping metadata validates the series ID, exact route
order and unique inline event names. The base loader selects the next mapped
event only after its predecessor's successful result has been saved. It calls
the original free-roam loader after stage four and for normal festival events
that encounter the private results branch. Normal-event regression runs remain
required before release. This remains base-disc code with owned DLC assets;
it does not require or execute the incompatible v4 update.

The progress record now supports version 3. One atomic write stores all 28
stage results, seven series results and the active attempt's four ordered
times. Stage four awards one series completion and best total. A retry retains
earlier stage times; retirement clears the active attempt while retaining
finished stage and series records. Legacy readers/migration, invalid order,
failed stage and cancellation writes, resume and duplicate-finish protection
have host regression coverage. Loading an older record alone does not rewrite it.
Partial totals must remain finite, and large valid times use bounded numeric
formatting so the saved checkpoint can still be parsed. Rejected samples leave
the earlier checkpoint unchanged.

The latest private series-7 runs complete four distinct native races with
the return-position guard and queued guest-call trap fix enabled:

| Route | Native event | Vulkan seconds | D3D12 seconds |
| --- | --- | ---: | ---: |
| 1 | 247 | 171.845762 | 171.114885 |
| 2 | 248 | 114.450466 | 114.346677 |
| 3 | 249 | 142.281128 | 142.135048 |
| 41 | 250 | 235.781409 | 237.540852 |
| **Series total and best** | | **664.358765** | **665.137463** |

Each run saves one series completion beside its isolated active profile.
The runner verifies ordered transitions, distinct race serials, stable native
finish times and matching saved records. Its `expect-rally-return-entry`
assertion observes four distinct live ColoradoDirt tracks, then newly loaded
Colorado track 317 after the final results. The original native position
(2002.928955, 143.791748, 960.038391) and forward vector stay unchanged through
all stages and the return. Both close the map and drive more than 30 metres;
final distances from that anchor are 138.47 metres on Vulkan and 133.95 metres
on D3D12. Reviewed captures show stage four at 65% and 139/134 km/h, then
Colorado terrain, traffic and the player car at 11/17 km/h respectively.
Use [the series scenario](../config/render-tests/fh1-rally-series-07.fh1test)
with a new `--series 7 --autopilot` seed. Other series remain unqualified.

A fresh private series-1 Vulkan trial earns route 11 in 143.386551 seconds
and loads route 10 with an advancing native timer. The second stage then
times out before a finish. The series is not qualified; its saved first-stage
checkpoint can be used to investigate the route-10 stall without awarding
synthetic results.

These runs supersede the earlier private series results and return failures.
Native tracing identified the original bug: at the first stage transition,
`CStoreRestorePlayerCarPosition` overwrote the valid Colorado entry with the
Rally finish. The guard suppresses only its store flag during mapped Rally
races and retains the original Enter/restore work. Earlier guard runs already
preserved the entry and loaded Colorado, but failed to close the loading map.
The corrected final script closes it before asserting movement. Missing world
observations, a wrong world and overwritten anchors have host regression
coverage. Synthetic final-stage fixtures helped diagnose this sequence but
do not qualify a full earned series.

Fresh completed-record reloads under the latest guest-call code pass on both
renderers. Vulkan retains 664.358765 seconds and D3D12 retains 665.137463
seconds as total and best, with one completion each. Both leave the ledger
bytes unchanged, close the map and drive more than 30 metres in Colorado,
then open/close the map again before the final return capture.

Fresh isolated checkpoint resumes under the latest guest-call code pass on
Vulkan and D3D12: a read-only copy taken after stage one starts route 2 as event
248, observes an advancing race timer and leaves the checkpoint bytes unchanged.
Fresh retirement runs resume that earned checkpoint, quit before finishing
route 2 and return
through the original free-roam branch. Route 1's earned result remains;
the active attempt clears without another stage or series award. Reviewed
returns show the original Colorado entry on both renderers. These retirement
checks also pass under the latest guest-call code.
Use the [resume](../config/render-tests/fh1-rally-series-resume.fh1test) and
[completed reload](../config/render-tests/fh1-rally-series-reload.fh1test)
scenarios with their corresponding private records, never the live AppData save.

Manual incremental builds had left the runtime build manifest stale. The
latest Vulkan full run keeps a separate receipt of its actual loaded executable
and DLL hashes. The latest D3D12 run uses refreshed local metadata containing
the actual executable hash, SSE4.1 baseline, repository revision and dirty SDK
revision. Neither is a clean release build. A base-disc Recaro race regression
also passes on Vulkan and the compiler-free D3D12 renderer under the updated
guest-call code: event 43 keeps the same player car/race serial, its native
timer advances and two running captures are more than 30 metres apart.
Reviewed captures show the eight-car race after the countdown. D3D12 required
a catalog captured from that saved-car route; the fresh-profile preparation
catalog alone lacked generated shader variants. The runner now accepts the
extractor's packed `corpus.blob` alongside legacy loose shader files, with
34 host runner checks passing. These are race-start/driving checks, not base
race completion or normal-event return qualification.

The content-root host test verifies
shared Marketplace enumeration/storage across profiles, ordinary saves in
the existing profile root and restoration of the default root when unset.

These are private progression foundations. Official Rally results/scoring,
XP, wristbands, unlocks, entry UI, pace notes, cars/upgrades, the other six
series and clean-release SDK integration remain acceptance work. Normal base
events and the full guest-call regression matrix also require qualification.

For pace-note implementation, the accepted owned main archive contains
`media/Tracks/ColoradoDirt/Ribbon_00/TrackRoute001.xml`. Its 26 `RallyCall`
entries supply trigger transforms, widths and 77 ordered samples. Every
sample ID maps to a group, cue and icon in owned `audio/VO/CoDriverAudio.xml`;
English (`EN`) and Mexican Spanish (`MX`) FEV/FSB banks are present. Validation
now covers all 28 championship routes: 682 trigger groups and 2,011 ordered
samples have finite transforms, positive widths, matching declared sample
counts and complete audio mappings. Reuse these authored inputs. Presence and
mapping are verified; playback, cue timing,
rewind/retry behavior and the HUD are not yet qualified.

The private seed builder's `--pace-notes` option converts the verified owned
route XML and loose co-driver audio mapping into `rally-pace.toml` inside the
new seed. No authored metadata or audio is distributed. The host scheduler
tests forward gate crossings, trigger width, geometric order, phrase order,
duplicate suppression, race changes, rewind re-arming, invalid positions and
teleport rejection. Its reader validates all 682 owned groups, including the
repeated exporter names in route 47; names are not unique trigger IDs.

`PINYON_SHIFT_RALLY_PACE_PROBE=EN|MX` enables a private native adapter. It
reads fresh presentation poses only in a mapped, running solo world and
serializes phrases using native playback-state checks. Multi-car player
identity, live rewind/retry, speech intelligibility and the HUD remain open.
The initial streaming-cue trial starts ordered phrases but hits the base
allocator's out-of-memory trap while opening another FSB stream; it is a
failed qualification. The adapter now uses the ordinary named-event cue
factory for authored FEV events. The corrected private English route-1
Vulkan trial passes 31 native cue starts and 10 complete authored phrases,
continuing past the streaming trial's failure point. Its eight-second
48 kHz, six-channel mix has RMS 0.064300 and peak 0.407971. Reviewed capture
shows route 1 at 30% and 166 km/h. A fresh Mexican Spanish D3D12 trial also
passes: 32 native starts, 10 complete phrases, RMS 0.067839 and peak 0.500748;
its reviewed capture shows 30% and 167 km/h. Both use the same locally built
base-disc adapter. English on D3D12 and Spanish on Vulkan remain unchecked.
`# expect-rally-pace EN` or `MX` checks imported cue references,
nonzero voices, phrase order and matching native completions for at least
two authored phrases, plus ordered non-silent native PCM. These checks do not
qualify speech intelligibility or the HUD.
Use [the pace probe](../config/render-tests/fh1-rally-pace-probe.fh1test)
with a fresh `--route 1 --autopilot --pace-notes` seed. Change its expected
language to `MX` in a private scenario copy for Mexican Spanish. The runner
has 42 host checks, including missing/out-of-order metadata, native voice
and mapping mismatches, overlapping/repeated phrases, missing completions
and missing, out-of-order or silent PCM. Host scheduler checks do not replace
live rewind, retry and stage-transition qualification.

The private adapter now publishes a copied phrase to the host UI thread and
draws the player's owned `CoDriverIconSet.xds` atlas. Five turn shapes cover
the mapped easy, medium, hard, square and hairpin calls; left turns mirror
their right-facing tiles. It shows the phrase's turn icons and marks the
currently spoken turn. Missing presentation updates suspend speech and clear
the HUD without forgetting crossed gates; a new race or exit still resets
the history, and a rewind re-arms gates after the restored time. Host checks
cover suspension, rewind during suspension, retry identity, phrase selection
and copied UI-state notifications. This remains opt-in diagnostic code.

Fresh English/Vulkan and Mexican Spanish/D3D12 route-1 tests pause during the
first phrase with a live native voice, each observe 66 frozen race-clock
samples, clear HUD dispatch, then resume later gates without replaying an
earlier call. Each passes 26 native starts, eight complete phrases and the
bounded PCM checks. The private
HUD dispatch uses the actual 1600x900 presenter target and a 1.25 scale for
the game's 1280x720 layout. Guest captures verify the pause menu and resumed
driving; they do not contain the host overlay. The native screenshot helper
fails to initialize after its recovery attempt, so visual HUD qualification
and other output sizes remain open. Use
[the active-phrase pause probe](../config/render-tests/fh1-rally-pace-pause.fh1test)
with the same fresh pinned route-1 seed. Its `# expect-rally-pace-suspend`
gate requires an interrupted voice, frozen clock, cleared HUD dispatch and
later calls without history replay. It also rejects stale speech/icons,
missing resume, non-finite or advancing clocks and changed race identity.

Native restart checks now pass for English pace notes on Vulkan and Mexican
Spanish on D3D12. Both restart route 1 through the native confirmation and
zero-clock pre-race menus, retain the same car serial, re-arm the first phrase
and continue to later gates: 22 native cue starts and six complete phrases each.
The checks observe 98/97 pre-race samples and preserve earned ledger bytes;
they do not finish the retried stage. Use
[the restart probe](../config/render-tests/fh1-rally-pace-retry.fh1test) with a
fresh pinned `--route 1 --autopilot --pace-notes` seed. The builder now invokes
the base game's disable action before enabling AI control, clearing a native
latch that otherwise leaves a restarted car driving into a wall. Existing
seeds need rebuilding to receive that preparation.

The progress observer also re-arms on native zero-clock pre-race even when the
car serial is reused. Host checks first reproduced a suppressed second finish,
then verify a second saved completion/best and reload, plus preservation of an
earlier championship stage during retry. Live championship retry and rewind
remain open. The initial D3D12 restart run failed on a missing pixel
variant; an error-free producer captured it, and a merged pack passes a fresh
compiler-free restart run. The expected loading fade is excluded from captures;
the renderer error and nonblank-image gates remain intact. These checks use
base .10 / media 2DC7007B and accepted owned DLC, with no v4 dependency.

Separate extended English/Vulkan and Mexican Spanish/D3D12 runs finish route 1
after an unfinished restart in 171.430336 and 171.486013 seconds, respectively.
Each saves exactly one completion in the active private profile's standalone
v2 ledger; the other stage records remain empty. Additional receipt checks
verify the two first-cue starts, intervening zero-clock reset, later calls,
native stable finish and matching saved result. Each run has 78 native starts
and 25 complete phrases. Both omit authored call index 3 (`redrockcorner004`)
out of route 1's 26 calls. Investigate actual gate crossing before qualifying
full-route playback; speech intelligibility, rewind and championship retry
remain open.

A separate English/Vulkan results-screen replay passes two native finishes
in the same process and with the same car serial, at 171.553836 and 171.571220
seconds. The active private ledger increments to two completions and retains
171.55383596172106 as its best. Additional receipt checks require both native
finishes, the intervening zero-clock pre-race, re-armed first cue, later gates,
and matching saved count/best; other stage records stay empty. The initial
trial confirmed RESTART but omitted START RACE and timed out; the passing
scenario includes both inputs. The Mexican Spanish/D3D12 equivalent also
passes two finishes, at 171.618472 and 171.551481 seconds, using the same car
and serial. Its ledger contains two completions and the improved best
171.55148113756914. Both runs have 153 native starts and 25 distinct complete
phrase keys across attempts; those keys do not establish complete coverage
of every authored call on each attempt.

Fresh native reloads on Vulkan and D3D12 preserve the respective twice-earned
record bytes, completion counts and best times while entering route 1 and
advancing its race clock. Use
[the stage reload probe](../config/render-tests/fh1-rally-stage-reload.fh1test)
with an immutable seed containing the previously earned active-profile ledger.
Its `# expect-rally-stage-reload 1` gate checks native loaded metadata against
that ledger, rejects changed bytes and new awards, and requires two advancing
running observations from the same stage, car and serial. Current host checks
pass 48 runner tests and eight seed-builder tests. Championship retry and
complete pace-note coverage remain open.

A private built-in overlay experiment uses `--builtin` with the seed builder
and `# expect-rally-builtin` in
[the first-stage probe](../config/render-tests/fh1-rally-builtin-first-stage.fh1test).
It stores the prepared
owned assets and stage/pace metadata under `cache/rally_adapter`, mounts them
through the existing file overlay and leaves `enabled_mods` empty. The runner
copies this specific prepared artifact into the private run without copying
unrelated shader caches. Its gate requires the normal `user` profile, one
owned-overlay mount, no mod load or modded-profile creation, and a saved ledger
inside that normal profile. It rejects an overlay error or enabled mods.
This experiment still borrows the Media Center prompt and Gauntlet race UI,
mutes the FR06 trigger and selects one fixed series; it is not production
Rally entry. Runtime presence checks also do not replace the launcher's verified
import and payload checks. A production preparation/ownership gate remains open.

Fresh English/Vulkan and Mexican Spanish/D3D12 built-in runs finish route 1
in 171.773157 and 171.930455 seconds respectively. Each saves one completion
and an active series-7 checkpoint with exactly one earned stage in the normal
profile, with no mods enabled or modded-profile tree. Separate receipt checks
match the checkpoint time to the native stable finish and reject other stage
or championship awards. Both have 75 native starts and 25 complete phrases;
the missing authored call and other pace/HUD qualification remain open.

Fresh-process resumes on both renderers load the earned first-stage checkpoint
from the normal profile and drive route 2 / event 248, preserving the respective
record bytes and first-stage total without a new award. Use
[the built-in resume probe](../config/render-tests/fh1-rally-builtin-resume.fh1test)
with a fresh immutable built-in seed containing a previously earned checkpoint.
The short resume check does not qualify route-2 completion, speech or UI language.

The base-disc audio probe loads the owned English FEV bank through the native
IAudioManager and creates a streaming `MedRight` cue. Its native Play method
starts a nonzero FMOD voice in the running route-41 diagnostic. This requires
the SDK's existing trap dispatcher for queued guest calls, keeping kernel
callbacks on the thread's live register context and restoring it afterward.
Mexican Spanish also starts the native cue during the full D3D12 series. An opt-in
render-test audio driver records eight seconds of the native six-channel
48 kHz PCM before SDL output, leaving normal playback intact. English and
Spanish full-series captures contain non-silent audio, with RMS 0.057984 and
0.057899 respectively.
This captures the full game mix; it does not isolate speech or qualify
intelligibility, route timing, rewind behavior or the HUD. Those remain open,
along with the full guest-call regression matrix.

Private scenarios may declare `# expect-rally-audio EN` or `MX`. The runner
enables the base-disc probe and checks ordered bank/cue/voice observations,
their matching language and handles, and the bounded capture's format,
duration and non-silent samples. Missing voices, wrong language/order/path,
silence, truncated files and mismatched signal statistics have regression
coverage. Use `--game-argument=--audio_mute=false` to enable device output when
running a hidden audio probe. Generated recordings stay in its private output;
no microphone or system-wide recording is used.

Car qualification must follow `ContentOffersMapping` and the imported licence
mask. The owned database separates masks 1, 2 and 4 for publication 1600;
the Focus SVT row (346) maps to the mask-4 offer, while the main mask-1 offer
maps the Escort (1272), WRX (365), Lancer (378) and 037 (1295), plus other rows.
Do not treat every newly merged `Data_Car` row as an owned selectable car.
Verify the normal merge and offer state before purchase/driving tests.

### Shared owned preparation and series-1 follow-up (2026-10-05)

`prepare-fh1-rally.py` now owns the asset work shared by launcher enable and
the private seed builder. It verifies the accepted package payload and original
licence, plus all three base executables and the pinned database/activity archive.
It publishes a fresh cache only after extraction and database work finish,
reuses matching verified output, and retains previous managed output on repair.
It does not alter entry triggers, AI, base event 43/race 42, profiles or mods.
The real owned-package preparation and reuse check passes for all 28 routes,
682 pace calls and 2,011 samples. Four preparation checks cover wrong base,
disabled/changed content, interrupted repair and launcher recovery; four import,
eight seed-builder, 48 runner and 33 release checks also pass.

The refactored builder's fresh normal-profile series-1 run on Vulkan saves route
11 at 142.944803 seconds and loads route 10 with native English speech, but then
times out waiting for stage 2 to finish. Its earned first-stage checkpoint is
retained, with no championship award. A separate fresh-process route-10 probe
also reaches a barrier at 41% progress with the car stopped. This is an AI
driving-probe limitation, not successful route/championship qualification.
Investigate the native AI path and qualify route 10 with player controls;
production entry/selection, scoring, XP and the rest of DLC-2 remain open.

### All-series director and named-entry resume (2026-10-05)

The owned cache now emits mapping version 4, naming all 28 native stage events.
The runtime derives each championship's authored four-stage order and handles
next-stage loading and resume without a fixed series. Legacy diagnostic mappings
remain readable. Selecting a different championship or standalone mode rejects
an unfinished attempt until explicit retirement succeeds; malformed progress and
failed writes preserve the previous ledger. Selecting alone does not write or
award progress. Preparation recipe 2 rebuilds older managed caches and retains
their prior contents.

The C++ progress test passes all seven championships in one profile, reopening
after each stage, plus invalid mappings, out-of-order starts, cross-series
switches, failed retirement, old-ledger migration and retry checks. A fresh
verified owned cache passes all 28 event/name lookups and reuse. Five preparation,
four import, eight seed-builder, 48 runner and 33 release checks pass.

A fresh private Vulkan resume uses the complete owned cache and a named first-stage
entry. It loads series 7's earned checkpoint, enters route 2/event 248, advances
the race clock and drives, preserving the ledger bytes with no new awards. The
native log confirms a 28-stage director instead of a fixed series. The captured
car reaches 107 km/h; the original pinned profile hash remains unchanged.
This still uses a private generic portal and base race UI. Normal entry/menu,
intro, official scoring/XP/unlocks, terrain, cars/upgrades and full route/audio
qualification remain open. This short resume does not establish their completion.

### Normal entry asset preparation and launch gate (2026-10-05)

Preparation recipe 3 generates seven generic activities at the owned Rally
activation locations and adds the guarded next-stage branch to the existing
festival results flow. It keeps the original career activation archive and base
event/race rows. Stage names now use the owned localized Events table; all 20
installed player languages are prepared. Nonempty base text survives the merge,
including three Traditional Chinese sponsor names that differ in the DLC table.
The owned lookup dictionaries remain intact when preserving those base strings.
The generic map markers still use a base activity icon; Rally presentation,
intro, selection/retirement UI and official results remain unfinished.

Normal `launch-preview.ps1` now verifies the enabled owned package, original
licence, supported base inputs and complete generated cache before giving the
runtime its prepared-entry flag. A failed verification stops launch with the
instructions to restore verified content. Saved cars with Rally parts require
that content; disabling it is not a general recovery path. Disabled/absent Rally does not
mount these assets. Private probes keep their separate opt-in flag.

[The entry-assets scenario](../config/render-tests/fh1-rally-entry-assets.fh1test)
passes on Vulkan through the same preflight, without the built-in probe flag.
It mounts one owned overlay, installs all 28 stages, loads the base world and
opens/closes its map in the normal profile. The earned Rally checkpoint retains
its exact bytes and receives no awards; the pinned source profile is unchanged.
This checks preparation, launch and map integration, **not activity activation or
stage completion**. Those native gates, base-race completion regression and the
remaining DLC-2 gameplay checks are still open. Host checks pass six preparation,
five string-table, four import, eight seed-builder, 49 runner and 33 release tests.

### Normal activity-entry follow-up (2026-10-05)

The native activity-start gate remains unqualified. Private placement fixtures
near series 3 and 4's owned activation coordinates fall below the terrain;
adding native road snapping, collidable reset and streaming waits does not
produce a stable start at those coordinates. A separate normal-profile launch
retains the copied series-3 return anchor but times out before entering a Rally
race. Capture-only passes from the placement fixtures do not qualify entry.

The `# expect-rally-entry N` gate requires normal launch verification, the owned
overlay, no mods, an advancing first-stage race and a fresh ordered seven-series
checkpoint without awards. The failed launch does not pass that gate. Keep the
prepared activation coordinates unchanged while investigating the native
entry/loading flow and Rally hub; these trials do not establish why activation
fails or whether those locations are physical free-roam destinations.

The base trigger parser only reads named world objects and ignored the owned
Rally entries' explicit X/Z coordinates. A guarded code-generation hook now
reads those attributes while the native XML reader is still inside the trigger
node. It applies only to the seven owned Rally generic activities. A fresh
normal-preflight Vulkan run passes free roam, map and return, and records all
seven coordinates exactly as supplied by the owned activation XML. The new
`# expect-rally-entry-positions` gate rejects missing, duplicate, invalid or
changed coordinates. This qualifies coordinate loading and map integration;
it does not qualify physical placement or activity activation.

Two normal series-3 start trials with the hook still fail. The first fixture
falls through terrain; the delayed-input trial moves away from the entry before
the input and stays in free roam, without a Rally checkpoint. Changing input
timing did not establish a reliable entry. The owned coordinates and radius
remain unchanged. The Release build, 52 runner tests and 33 release-contract
tests pass; normal entry and full Rally support remain open.

### Owned co-driver activation without an override (2026-10-05)

Verified owned Rally preparation now enables the existing co-driver scheduler
and HUD source without `PINYON_SHIFT_RALLY_PACE_PROBE`. The speech bank follows
the console language and country, including Mexican Spanish for Spanish/Mexico;
UI languages without an owned speech bank fall back to English. Disabled or
absent Rally does not enable this owned-content path. Private language overrides
remain available for diagnostics.

[The owned-pace scenario](../config/render-tests/fh1-rally-owned-pace.fh1test)
checks default activation with `# expect-rally-pace-default EN` or `MX`. It
clears inherited pace overrides and requires the owned overlay, normal profile,
console-locale selection, ordered native voices and a non-silent eight-second
PCM capture. It rejects mod isolation and the old single-cue injection. PCM
recording remains test-only; ordinary play uses the existing audio output.

Fresh English (`user_language=1`, `user_country=103`) and Mexican Spanish
(`user_language=5`, `user_country=71`) Vulkan runs each pass 32 native cue starts
and 10 complete authored phrases. Their six-channel 48 kHz captures have RMS
0.068103 and 0.067717 respectively. Both use the private generic entry fixture
with no mods and no pace-language override. This qualifies default scheduling
in that fixture, not normal activity entry, speech intelligibility, visual HUD,
live rewind, all banks or full Rally gameplay. Those checks remain open.

The Release executable and C++ pace tests build successfully. The C++ tests
validate the console-locale mapping and all 682 owned authored calls; 51 runner
and 33 release-contract tests pass. The pinned source profile is unchanged.

### Hub selection and player-menu entry (2026-10-05)

The authored activations belong to `ColoradoDirt`. Read-only inspection of the
original Rally flow also shows a hub selecting events while world presentation
is disabled. Those X/Z values do not establish physical entry destinations in
normal Colorado. The base-disc adapter now queues a championship selection
through the already prepared native generic activity, retaining its loading,
game-control and return-position work. It waits for a live world before offering
selection and requires the native loader's idle state before starting. A menu
pause retains that verified readiness. No v4 input is used by this runtime path,
and no owned coordinate, radius, source save or generated cache is altered.

The existing in-game menu now contains Horizon Rally when verified owned Rally
is active. It lists seven numbered championships, shows the unfinished stage,
prevents selecting another unfinished championship, and offers retirement with
a confirmation that defaults to keeping the attempt. The follow-up below
qualifies keyboard resume and retirement for championship 7. Localized
championship names and original Rally presentation remain open.

A fresh private API trial first passes series 7's initial stage entry. A separate
[player-menu scenario](../config/render-tests/fh1-rally-hub-entry.fh1test) then
passes keyboard navigation through Settings and Horizon Rally, menu release,
native selection and driving in route 1/event 247. This second run uses normal
launch preflight, the complete owned cache, the unchanged base save, no mods and
no private hub or built-in probe. Native world fields change from mode 17,
track 317, Colorado to mode 3, track 1148, ColoradoDirt. Its initial seven-series
checkpoint saves with no completion awards. Both menu layouts fit the safe area.
The actual guest driving capture was reviewed; it does not include the host
menu, so visual menu review remains open.

The first API trial started too early during initial loading. The first player
menu trial waited indefinitely for vehicle presentation after the menu pause.
Both failed; they are superseded by the readiness and loader-idle guards above.
The final Release build, 52 runner tests and 33 release-contract tests pass.
The pinned source profile retains its original hash. This qualifies keyboard
entry into the first stage of championship 7 only; it does not complete DLC-2.

### Player-menu resume and retirement (2026-10-05)

The [resume scenario](../config/render-tests/fh1-rally-hub-resume.fh1test)
passes keyboard selection of championship 7 after a previously earned first
stage. Native route 2/event 248 starts and advances, the car drives, and the
171.773157-second checkpoint remains byte-for-byte unchanged. The normal owned
overlay and all-stage loader pass launch preflight, with no mods or private hub
or built-in probe. This uses an actually earned checkpoint, not invented results.

[Stage-one resume](../config/render-tests/fh1-rally-hub-resume-first.fh1test)
also passes from the previous normal player-entry run's initial checkpoint.
Route 1/event 247 starts and drives while the zero-completion attempt remains
unchanged. The native loader now reports this resume even when its stage name
needs no substitution; the runner accepts a valid zero-time initial attempt.

The [retirement scenario](../config/render-tests/fh1-rally-hub-retire.fh1test)
keeps the first confirmation using its default selection, then explicitly
retires the same championship. The unfinished attempt clears while all earned
stage and championship records remain unchanged. After closing the host menu
and dismissing the base pause menu, normal free-roam driving resumes. An earlier
trial qualified only cancellation and left that pause menu open; it did not prove
post-retirement driving. The expanded gate requires safe confirmation layouts,
menu release, two free-roam captures and at least 30 metres of movement.

All runs use private state copies on Vulkan and preserve the source ledger and
pinned profile. Guest driving captures were reviewed; host-menu visual review
is still open. The final Release build, 53 runner checks and 33 release-contract
checks pass. These qualify championship 7 keyboard flows for stages 1 and 2;
controller/mouse behavior, other championships, full results, Rally cars and
upgrades, official scoring/unlocks and the remaining DLC-2 checks remain open.

### Native Rally car database and entitlement check — 2026-10-05

The supported base title already merges Rally's car, upgrade and offer tables
through its normal Marketplace flow. A test-only, read-only native query now
compares that live database with the verified owned package. No replacement car
tables or additional ownership grants are needed. All 16 car rows and their
tyre compound, spring/damper and engine option counts match the package.

The native entitlement cache independently applies the imported licence mask
`00000001`. Five owned cars are selectable: Escort RS Cosworth, Lancia 037,
Toyota Celica, Mitsubishi Lancer and Subaru WRX. The Focus SVT belongs to the
separate season-pass offer with mask `00000004` and remains unowned and hidden.
Ten additional authored car variants remain nonselectable. The raw car table's
`IsPurchased` column alone does not establish ownership; the native offer cache
is checked separately.

`fh1-rally-car-database.fh1test` passes on Vulkan with normal owned-content
preflight, all 28 stage mappings and no mods or entry probes. It preserves the
source's earned Rally ledger byte for byte. The gate rejects missing/duplicate
rows, wrong entitlements, mismatched upgrade counts and any progress award.
The Release build and 54 runner plus 33 release-contract checks pass.

This qualifies the native database merge and imported Rally entitlement only.
Autoshow visibility and purchase, garage rendering, driving, usable upgrades,
save/reload and safe disable with a purchased DLC car remain open. The initial
Autoshow trials encountered the save's new Showcase notification and map instead
of race car selection; their captures do not qualify the purchase flow.

### Complete saved garage fixture — 2026-10-05

The earlier owned-content fixture copied only `ForzaProfile`, omitting its
companion `PlayerDatabase`, `VersionFlags`, livery and thumbnail files. Those
tests retain their database, entitlement and separate Rally-ledger evidence,
but do not qualify preservation of the player's existing saved garage. The
profile-only fixture loaded a fallback Corrado instead of the saved Mazda and
did not expose the expected Gauntlet activity. Full-save gameplay and persistence
must be checked with all companion files present.

A fresh private fixture now copies the complete pinned profile directory,
verifies every source file by SHA-256 and retains the natively earned Rally
ledger unchanged. The original pinned seed and AppData save remain untouched.
With that fixture, the normal Gauntlet entry, saved Mazda selection and race-to-
Autoshow recommended-car flow pass on Vulkan. The native Rally database and
licence gate also passes with the complete saved garage present. Earlier menu,
stage and progression probes still require full-save qualification; purchase,
driving, upgrades and reload remain open.

### Owned Escort purchase, reload and driving — 2026-10-05

With the complete saved garage present, normal map fast travel and Autoshow
manufacturer selection expose the owned 1992 Escort RS Cosworth, C314. Its
portrait and showroom model render correctly. Buying with credits deducts
24,000 from the original 167,700 balance and saves the car in garage slot 7
with a new thumbnail. The existing livery and thumbnail files remain unchanged.
No credits, vehicle records or ownership flags are manufactured.

A fresh private copy of that natively saved state reloads the Escort, garage
slot 7 and 143,700-credit balance. Actual Vulkan captures show the car driving
at 50 km/h; recorded free-roam positions move 106 metres. The native car
database/licence gate passes again and the earned Rally ledger remains intact.
The pinned snapshot and live AppData save are preserved separately; the live
save is newer than the snapshot and their hashes are not assumed identical.

This qualifies one owned Rally car's purchase, persistence and basic driving,
not the other four cars or their upgrades. A hidden-window replay missed the
Autoshow map icon and stayed on the map despite passing its declared database
gate; those captures do not qualify purchase. The successful purchase and
reload use visible-window runs. Garage upgrade installation and persistence,
safe disable, full-save Rally stage/progress checks and remaining DLC-2 gates
are still open.

### Upgrade menu reload repair — 2026-10-05

Loading the saved car previously skipped the base game's transient upgrade-view
initialization. **Custom Upgrade** queried the missing Areas view, received a
null recordset and crashed. The fresh-load hook now calls the ordinary native
initializer after the car enters its cache. It reuses the player's current
garage record and creates the native Parts, Types and Areas views; it does not
manufacture parts, ownership, credits or garage entries.

The normal build opens the saved Escort's **Custom Upgrade** and **Tire Compound**
menus on Vulkan with the complete private save. Native SQL preparation succeeds
for the views and menu queries. A base-car control also opens the already owned
Mustang's Custom Upgrade after a native car change. The manual regression route
is `config/render-tests/fh1-rally-car-custom-upgrade.fh1test`; its database gate
alone does not qualify the captured menu or upgrade installation.

### Rally upgrade definitions and tyre purchase — 2026-10-05

Owned-content preparation recipe 5 adds the missing level-5 tyre and level-4
suspension/transmission menu definitions. The native option query can now join
the imported Rally parts to their menu entries. The tyre compound uses the
verified Rally parameters and existing base affect/friction curves; all 61
compound fields match the inspected behavior reference. Compounds used by base
cars remain unchanged. The preparation requires the verified base dump and owned
Rally package, without a title-update dependency.

The generated menus use project-authored English and Spanish text; other
languages currently fall back to English for these three upgrades. Existing
base upgrade icons are reused. The actual parts and suspension/transmission
data still come from the imported owned package.

The Escort's Rally suspension preview and purchase also render in Mexican
Spanish, with the imported part's ride-height increase and native discounted
price. Buying costs 930 credits after the save's 85% discount, moving C339 to
C341 and 142,200 credits to 141,270. Leaving Custom Upgrade commits suspension
part `1272004` and the native purchased-part entry; the installed tyre remains
`1272005`, with a combined parts value of 2,430. Stopping in the leaf menu only
shows the pending purchase and does not qualify persistence.

On Vulkan, the Escort's **Rally Tire Compound** preview and normal purchase
confirmation render correctly. Buying deducts 1,500 credits after the save's
native 85% discount: 143,700 becomes 142,200. The installed menu shows C339 and
the native saved garage records tyre part `1272005`, plus the corresponding
purchased-part entry. Existing garage slots 1–6, earlier purchased parts and
the earned Rally ledger remain unchanged.

A fresh private reload retains that saved part and balance. Native SQL tracing
confirms the game requests compound 9 successfully. The initial free-roam
attempts hit garage barriers; those runs establish reload and compound
selection, not sustained driving.

A fresh copy of the natively saved tyre-and-suspension state loads an identical
decompressed player database, retaining both parts, garage slot 7 and 141,270
credits. Normal Horizon Rally menu entry resumes the earned championship-7
checkpoint at stage two (event 248). Reviewed Vulkan captures show the Escort
driving at 51–52 km/h and reaching 2% progress, with 134 metres of displacement.
Compound-9 SQL preparation succeeds again. Existing garage rows, earlier
purchases, original livery/thumbnails and the earned Rally ledger remain intact;
the upgraded car receives its own refreshed thumbnail. This qualifies purchase,
save/reload and initial Rally driving with the two parts, while full-stage
completion, actual Rally surface handling and transmission installation remain
open. A database gate alone does not establish those gameplay checks.

### Rally transmission purchase and combined upgrade reload — 2026-10-05

The owned Escort's **Rally Transmission** preview, purchase and installed menu
now pass on Vulkan. The native preview shows a 0.15-second shift-time reduction
and C343. Buying costs 930 credits after the save's existing 85% discount:
141,270 becomes 140,340. Leaving Custom Upgrade saves transmission part `676004`
and its purchased-part entry, alongside tyre `1272005` and suspension `1272004`.
The combined parts value is 3,360. Original garage slots 1–6 and earlier purchased
parts remain unchanged. The reproducible route is
[`fh1-rally-car-transmission-upgrade.fh1test`](../config/render-tests/fh1-rally-car-transmission-upgrade.fh1test);
its database gate requires separate capture and native-save review.

A fresh Mexican Spanish Vulkan run loads a byte-identical decompressed player
database with all three parts and the saved balance. Normal menu entry resumes
the earned championship-7 stage-two checkpoint. Reviewed captures show the Escort
at 47–45 km/h, 2% progress and 134 metres of displacement. The earned Rally ledger,
source saves, original livery and original thumbnails remain unchanged. This
qualifies the Escort's three native purchases, save/reload and initial driving;
tuning, sustained surface handling and full saved-garage stage completion remain
open. The other four owned Rally cars and base-car conversions still need work.

The first transmission test navigated to **Engine / Race Fuel System** and bought
that part in its private copy. Its database gate passed, but reviewed captures
exclude it from transmission qualification. The corrected route selects
**Drivetrain / Transmission** and uses a fresh copy of the untouched source.

### Base-disc Rally tyre conversions — 2026-10-05

Owned Rally preparation recipe 6 derives 173 level-5 tyre parts from the verified
base's existing race-tyre rows. It retains each car's mass/aero and manufacturer
fields, selects Rally compound 9, and uses the native 10,000-credit list price.
Every generated field matches the inspected behavior reference. Original part
rows remain unchanged, including factory race tyres; the Ferrari 599XX's missing
Rally conversion remains excluded. Preparation uses the verified base and owned
Rally inputs and does not need a title update at runtime.

An already owned Mustang Boss 429 (car `404`, garage slot 2) now offers **Rally
Tire Compound** in the normal upgrade menu. Buying with the existing 85% discount
costs 1,500 credits: 143,700 becomes 142,200, C400 becomes B417, and the native
save records tyre part `404005` plus its purchased-part entry. Other garage rows,
prior purchases, the original livery and the other cars' thumbnails remain intact;
the Mustang's thumbnail refreshes normally. The reproducible manual route is
[`fh1-rally-base-car-tyre-upgrade.fh1test`](../config/render-tests/fh1-rally-base-car-tyre-upgrade.fh1test).

A fresh Mexican Spanish Vulkan run reloads the exact saved decompressed player
database and balance, resumes the earned stage-two checkpoint through the normal
Rally menu, and drives 107 metres. Reviewed captures show 40/32 km/h and 1% progress.
Native compound-9 preparation succeeds. Source saves and the earned Rally ledger
remain unchanged. This qualifies one base car's tyre purchase/persistence and
initial driving, not all 173 cars' handling, tuning, suspension, transmission,
safe disable or full-stage completion. Base Rally suspension physics rows are
absent, so those conversions need further work beyond adding menu entries.

### Missing saved Rally tyre recovery — 2026-10-05

Disabling Rally after the native Mustang tyre purchase reproduced a startup
access violation: the base game dereferenced an absent tyre-physics record.
The constructor now checks that required record before the dereference and
stops with instructions to re-enable or restore the missing DLC. It retains
the purchased part instead of substituting stock tyres or rewriting the save.
The launcher presents this as missing saved content, keeps the DLC panel
available and does not create a crash report. Rally preparation errors also
direct the player to restore verified content rather than assuming a saved
car can run without Rally.

A fresh Vulkan negative test returns the controlled missing-content result,
with no access violation or crash files. All 12 profile files match the
immutable private seed. Re-enabling Rally in a separate copy and fresh-loading
the game retains tyre `404005`, garage slot 2, the exact saved player database
and 142,200 credits. Normal stage-two resume and initial driving pass again;
reviewed captures show 40/32 km/h and 1% progress. This checks disabled-content
recovery for this saved tyre; missing DLC car models, suspension/transmission
records and complete disable/uninstall qualification remain open.
An independent private Vulkan control starts the same base car with stock tyre
`404001` and Rally disabled; this is a startup check, not a full base-race gate.

### Selected Rally car disable, save and restoration — 2026-10-05

With the natively purchased stock Escort selected, disabling Rally lets the
base game fall back to the original Corrado. A startup-only private Vulkan run
leaves all 12 profile files unchanged. A further run reaches Dak's Garage,
selects the existing Mustang and saves that selection normally. It retains
all seven garage records, all 122 purchased-part rows, the Escort's original
parts and the 143,700-credit balance. The fallback Corrado's ordinary driven
time increases; no vehicle or ownership record is manufactured or removed.

After re-enabling the verified package in another private copy, a fresh native
load reads the exact player database saved with Rally disabled. The original
Escort appears in the garage with its correct card/model and can be selected
again without repurchase. Leaving the service, then using the normal Rally
menu, resumes the earned championship-7 stage-two checkpoint. Reviewed captures
show 51 km/h, 2% progress and 134 metres of displacement. The purchased-part
records, balance, earned Rally ledger, original livery, source seeds, pinned
save and newer AppData save remain intact. Ordinary driven times and the
selected cars' thumbnails may refresh through native saves.

The reproducible routes are
[`fh1-rally-disabled-selected-car.fh1test`](../config/render-tests/fh1-rally-disabled-selected-car.fh1test)
and [`fh1-rally-restored-selected-car.fh1test`](../config/render-tests/fh1-rally-restored-selected-car.fh1test).
Their runtime gates require separate capture/native-save review. Early scripts
missed startup navigation or selected the Audi instead of the Escort; those
receipts do not qualify the intended garage selection. A longer replay also
confirmed that starting Rally while the native garage menu is open leaves
loading pending; the passing route exits with Back first. The subsequent native
control guard and its regression run are described below. Existing older striped car thumbnails are the known
[profile-thumbnail issue](../BUGS.md), not evidence that their preserved files
were repaired.

This qualifies disable/save/restore for one stock owned Rally car. Other DLC
cars, a selected Rally car with purchased upgrades, actual uninstall, full-stage
completion and the remaining Rally gameplay gates remain open.

### Rally entry from native services — 2026-10-05

Mode 17 and an idle loader also occur inside Dak's Garage. Native
`CIsGameControlInUse` tests the owner at the start of `CGameControl`
(`0x832E4A9C`); read-only snapshots confirm that driving has no owner and the
garage retains the `workshop_02` state instance's token. The host menu's
`XN_SYS_UI` notification separately acquires control through the native
`pause` instance. Entry now rejects service owners while preserving a ready
free-roam world across that host pause. The queued guest action rechecks the
owner and clears rejected selections. No service input or game-control token
is manufactured or released by the adapter.

The new
[`fh1-rally-service-entry-guard.fh1test`](../config/render-tests/fh1-rally-service-entry-guard.fh1test)
passes on Vulkan in private session `20261006T024017Z-p9768`, build SHA-256
`2E57A5B8F9CF394DF2CFBE9DB3DD1AD34909E25C0348FA67781BE9FCDD9884BD`.
It selects the previously purchased Escort, opens F6 over Dak's Garage and
attempts the disabled Rally action. Native control remains owned by
`workshop_02`; the Rally page stays open and no entry is queued. After closing
F6 and leaving the garage, availability returns. A new player menu selection
then resumes the earned championship-7 stage-two checkpoint. Reviewed captures
show the same Escort driving at 51 km/h, 2% progress and 134.5 metres of motion.

The native load matches the exact database previously saved with Rally
disabled. The run preserves all seven garage rows, all 122 purchased parts,
143,700 credits and the earned Rally ledger; only the Mustang and Escort's
ordinary driven times increase during their use. The immutable source seed,
purchased-car source, pinned AppData seed and live AppData save remain unchanged.
The private result includes the control-guard, resume and race-HUD checks plus
a separate native-save audit. The render-runner's 56 host tests pass.
This qualifies the garage guard and restored initial driving for this case;
other service contexts, full saved-garage stages and championships remain open.

### Saved-garage native finish and checkpoint reload — 2026-10-05

The complete seven-car profile now passes a championship-7 stage-two finish
through normal F6 entry on Vulkan, with the stock owned Escort. The
`fh1-rally-full-garage-stage-finish.fh1test` scenario uses
`--fh1_render_test_rally_ai_driver=true`: a default-off diagnostic that invokes
the native car-controller switch after the race starts and is ignored outside
render tests. The runner explicitly reports diagnostic AI and leaves player
steering unqualified. It does not modify physics, clocks or finish flags.

Private session `20261006T025254Z-p35208` finishes natively in
127.81701390467433 seconds, saves exactly one route-2 completion and advances
the earned checkpoint to stage three with a total of 299.5901708414582 seconds.
No championship completion is awarded. There are 44 native pace-play and 44
pace-finished events; speech intelligibility and other routes remain unchecked.
The finish menu renders, but its background shows the underside of the terrain.
The vehicle position remains stable across the results captures. The cause was
unconfirmed in this run; the subsequent camera fix is recorded below.

A fresh process, `20261006T030023Z-p16708`, runs
`fh1-rally-full-garage-stage-reload.fh1test` without the diagnostic AI flag.
Normal F6 resume loads stage three, preserves the ledger byte for byte and
drives the Escort 170.9 metres under scripted throttle. Both runs use build
SHA-256 `635686709A452EE0EF8968EE9ECEB8EC18024C8BB85E9646A843581079A69DB0`.
The loaded native database matches the preceding native save exactly. All seven
garage rows, 122 purchased parts, 143,700 credits and the selected Escort survive;
only its ordinary driven time increases. The source state, pinned seed and live
AppData profile hashes remain unchanged. A separate local native-save audit
records these assertions alongside the runner receipts; its 57 host tests pass.

This qualifies one diagnostic saved-garage finish and fresh-process checkpoint
resume on the supported base disc. At this point, manual full-stage handling,
the results background, official rewards/unlocks, remaining stages and full
championships remain open. All subsequent qualification targets Vulkan;
legacy Direct3D 12 receipts do not gate this work.

### Rally finish-camera height — 2026-10-05

Read-only native camera snapshots select `postrace_finishline_RALLY_002` and
its authored `CameraTargetNode_0`. The native animated camera's X/Z and relative
height agree with its owned animation keys. The target disables ground snapping
and places its origin at `(-6247.250977, 315.620697, -4790.416504)`.
A temporary render-test diagnostic invokes the native node transform and terrain
query on a copy of that node. Private session `20261006T035102Z-p37216`, build
SHA-256 `EAB6FD689041F69492A7C5BB9F10ABA464BDB1A508C1E73FE4CF2D217D9FD43E`,
measures ground at `328.128784`: 12.508087 metres above the authored height.
The active camera, original node and owned input files are never changed by
that measurement. Earlier probe attempts yielded no valid ground sample.

Preparation recipe 7 enables the existing `snapToGround` flag only on camera
nodes referenced by Rally finish sequences. It preserves positions, rotations,
parents, animation keys, prerace sequences and unrelated nodes. Comparing all
29 owned camera files against their generated derivatives finds exactly 92
flag changes and no other camera-data changes. Existing managed caches rebuild
through the atomic preparation path and retain their previous contents. The
temporary C++ probe has been removed; the normal executable again has SHA-256
`635686709A452EE0EF8968EE9ECEB8EC18024C8BB85E9646A843581079A69DB0`.

The full saved-garage finish scenario passes on Vulkan in private session
`20261006T035655Z-p38092`, using normal F6 entry and the diagnostic native AI
driver. Its native finish is 127.855652 seconds. Both results captures, 83.33
seconds apart, show the road and surrounding terrain correctly. A read-only
camera snapshot measures Y `329.313873`, up from `316.805786`, with identical
X/Z. The native save audit retains seven garage cars, 122 purchased parts,
143,700 credits and the selected stock Escort, changing only its ordinary
driven time. Exactly one route-2 completion advances the earned checkpoint to
stage three; no championship completion is awarded. Source-state and live
AppData hashes remain unchanged.

Fresh process `20261006T040319Z-p17444` passes the stage-three reload scenario
with recipe 7 and without the diagnostic AI flag. Its loaded native database
matches the preceding save exactly, all seven cars and 122 parts remain, and
the earned ledger is byte-identical. Scripted throttle drives the stock Escort
170.934 metres, with reviewed captures showing 53 km/h and later 3% progress.
Without scripted steering it stops against the roadside barrier; this remains
initial player-control qualification, not full-stage handling. The finish-run
source profile, original source state, pinned seed and live AppData hashes all
remain unchanged. Both runs have separate native-save, asset and visual receipts.

One preceding diagnostic run finished natively but failed the runner because
the capture inside loading was black. The full finish scenario now omits that
transient capture while retaining the loaded-profile, race-HUD, both results,
normal-entry, native-finish and earned-progress checks. All 67 import,
preparation and render-runner host checks pass, including preservation of
owned camera inputs and unrelated camera data.

This fixes the reproduced stage-two background. Other finish views, manual
full-stage handling, official rewards/unlocks and remaining Rally gameplay
gates remain open. No v4 input or legacy Direct3D 12 qualification is required.

### Saved-garage stage-three finish — 2026-10-05

The full finish scenario also passes stage three on Vulkan, starting from the
preceding earned checkpoint with normal F6 entry and the stock owned Escort.
Private session `20261006T040918Z-p35600` uses the same normal executable
SHA-256 `635686709A452EE0EF8968EE9ECEB8EC18024C8BB85E9646A843581079A69DB0`
and preparation recipe 7. The diagnostic native AI finishes route 3 in
155.48901850519889 seconds. Both results captures, 83.33 seconds apart, show
the road and surrounding terrain correctly.

A separate native-save audit finds an exact match with the preceding loaded
database, seven garage cars, 122 purchased parts, 143,700 credits and the
selected stock Escort. Only its ordinary driven time increases. The first two
earned stage times remain unchanged; exactly one route-3 completion advances
the attempt to stage four with total 455.11782703159605 seconds. No series
completion is awarded. Earlier source-state and live AppData profile hashes
remain unchanged, and the final-stage source profile is pinned read-only.

The new `fh1-rally-full-garage-final-stage.fh1test` reuses the existing native
finish wait and results/free-roam navigation for the earned 7/4 checkpoint.
Its longer output-frame route is required for that final stage and native
readiness waits; it does not qualify wall-time performance or player steering.
The first final-stage run, session `20261006T041631Z-p18308`, crashed before
finishing route 41 / event 268 at native race time 186.333010 seconds. Its
crash report records a guest null-data read at `0x00000038` inside audio
function `sub_830072D0`; the lifetime fault is still under investigation.
This run earns no final-stage or championship qualification. Completion,
its finish background and return remain open; the preceding completed
stage-three source is preserved for a fresh private run after the fault is
resolved.
Official Rally rewards/unlocks, manual handling, other championships and the
remaining DLC gates remain open.

### Rally audio update ownership — 2026-10-05

The first normal saved-garage final-stage run crashed in the native FMOD
channel-settings update. A read-only diagnostic rerun showed cue cleanup on
guest thread 33440 while the channel update ran on thread 25852. Native
cleanup `sub_82FA84E8` clears the channel's shared-settings pointer; the
failing update `sub_830072D0` reads that pointer repeatedly. The rerun did
not reproduce the crash, so the observed failure is intermittent.

The adapter now publishes pace observations from the frame thread and
performs cue operations through the title's existing `CAudioEngine::Update`
(`sub_82BB5918`), before its ordinary FMOD update. It retains the SDK trap
dispatcher to preserve the live guest register context. An owned-pace runner
check now rejects cue lifetimes that run outside that native audio thread.
The Release build and 58 render-runner checks pass. Private session
`20261006T044444Z-p34384` records 98 pace plays and 98 finishes on audio thread
35528, matching the native channel update and all 120 diagnostic property
observations. It records no pace error or audio crash. Route 41 finishes in
261.4848118697364 seconds and saves one championship-7 completion, retaining
the preceding three stage times, with total 716.6026389013325 seconds. The
results background shows the road and terrain. The return movement check
still fails: reversing without steering moves only 3.015793 metres from the
parked garage anchor. This is not an overall passing qualification.

A read-only native-save audit confirms that its loaded database matches the
preceding stage-three save and retains seven garage cars and all 122 purchased
parts. The selected stock Escort receives native distance, driven-time and
race statistics; the other six cars remain unchanged. Native winnings increase
credits from 143,700 to 144,960, with 1,260 recorded on that car. These observed
base-title awards do not qualify official Rally championship rewards or unlocks.

The temporary read-only audio property probe has been removed. The normal
Release build passes with executable SHA-256
`E21D44E694067FA32E3E1498E11E34CC16FDECAE6B30BB9092C858D16EFC5D0A`.
Three initial fresh-process Vulkan reloads from the actual completed private save,
without diagnostic AI, restored the stock Escort at the original garage
anchor. Their departure checks failed: continuous reverse with full steering
moved 8.647689 metres; a brief turn followed by straight reverse moved
21.080320 metres before another barrier; and a longer reverse turn followed
by straight forward throttle moved 3.781810 metres from its post-turn wait
anchor. Captures show ordinary garage-area barriers. A departure maneuver
and passing completed-series reload remain open. Full-stage player handling
remains unqualified.

Those initial reload scripts omitted `expect-rally-normal-entry`, so the
render runner bypassed ordinary owned-content preparation and attempted the
private probe's absent stage mapping. They establish native car movement and
garage collisions only; they do not qualify loaded Rally progress. A corrected
normal-entry run loads all four saved stages and clears the garage area, but
the completed-series receipt is absent because diagnostics reported only a
selected championship. The receipt now also reports the last completed
attempt when the hub has no selection. A host regression reloads that state
without selection, replay or another award, and leaves the ledger unchanged.

The preceding diagnostic session `20261006T043323Z-p35208` finished route 41
in 261.5459619120146 seconds and saved one championship-7 completion, retaining
the first three earned times. Its final results background shows the road and
terrain. It returned to the original garage anchor, but its forward-only
movement check stopped against the barrier already facing the parked car;
the runner failed with 4.940862 metres of movement. This is not an overall
passing qualification. The route now attempts reverse departure from that
preserved anchor before its ordinary player-movement check; that departure
remains unqualified. The stage-three source and live
AppData profile hashes remain unchanged.


### Completed saved-garage championship reload � 2026-10-05

`fh1-rally-full-garage-series-reload.fh1test` passes on Vulkan in normal Release
session `20261006T052036Z-p36592`, executable SHA-256
`3832206D94DD6E841D08C5531F054BF7C30337C0BA52AEE4550092593E8286F4`.
It uses ordinary owned-content preparation and no diagnostic AI or mods.
The four native-earned stage times and the single championship-7 completion
reload unchanged, with total and best 716.6026389013325 seconds. The native
loaded player database exactly matches the final-stage save: seven cars,
122 purchased parts, 144,960 credits and the selected stock Escort. Only its
ordinary free-roam distance and driven time may change in the audited
native snapshots; the ledger remains byte-identical.
No additional stage completion, retirement or award is recorded.

The route uses ordinary reverse, handbrake, forward throttle and steering to
clear the preserved garage anchor. The Escort moves 85.74659505472316 metres
before the driving capture, then opens/closes the map and returns to Colorado
free roam. Captures show the correct car, terrain and HUD. This qualifies
initial free-roam controls after reload, not full-stage player handling.
The live AppData save, pinned complete profile, stage-three source and actual
completed source all retain their recorded hashes.

Startup diagnostics now report the last completed attempt even when the
normal hub has no championship selected. This does not select or restart a
series. The host progress test reopens a completed ledger without selection,
checks its four-stage total and single completion, rejects a stale finish,
and verifies that its bytes remain unchanged. The test and Release build pass.

The full final-stage scenario now uses the same garage departure. A new normal
Vulkan run from the preserved earned 7/4 checkpoint is in progress, without
the temporary audio property probe. Its end-to-end completion, audio lifecycle
and return still require a passing run and separate native-save audit. The
preceding final-stage run remains an overall failure despite its earned save.
Official rewards/unlocks, full-stage manual handling, the other championships
and remaining DLC gates remain open.

### Complete-profile October fixture � 2026-10-05

A new private October seed copies all ten pinned profile/garage files and
imports the player's accepted package through the normal management tool.
Imports start disabled; enabling retains the original `FFFFFFFF` licence mask
and SDK-compatible header. The seed and pinned source profile hashes match
before and after import/enable. The owned merge database contains eleven car
rows, including LCE variants; its raw `IsPurchased` flags are not entitlement
proof. Native offers, Autoshow visibility, purchase, rendering, driving,
upgrades and save/reload still need qualification with this complete fixture.
No Rally package or v4 update is required for that car-pack test.


### Original Rally entry flow traced (2026-10-06)

Read-only comparison of the base game-mode archive and the verified local
update-media behavior reference identifies the original player entry path:
the pause screen emits `onRally`, its flow switches audio and invokes
`global.load_into_rally_free_roam`, and `CLoadIntoRallyFreeRoam` loads the
Rally hub. The hub disables world presentation and uses
`CShowUIScreen_RallyHub` for championship selection, car selection/purchase,
return and outpost actions. Race Central also has a Rally hub return path.
These are reference findings, not a runtime dependency on the supplied v4.

The next porting slice is the native pause entry, hub loader and hub UI
behaviors, followed by original intro and event selection. The current F6
championship rows do not implement this slice. Do not reinterpret all seven
`ColoradoDirt` activation coordinates as normal Colorado driving destinations:
physical activation must be restored in the context the original flow uses.
Manual entry, car selection, full championship rewards/unlocks and persistent
original-flow resume remain open.

The comparison receipt and extracted XML are retained locally under
`.local/dlc/reference/original-entry-20261006/`; only this behavior summary is
tracked. No original assets, AppData save or existing device progress were
modified by the reference inspection.

### Original Rally hub asset inventory (2026-10-06)

A read-only inventory of the verified owned package finds Rally marketplace
art and car thumbnails, but no Rally hub scene in its four archives. The
update-media behavior reference contains a seven-ticket hub, car eligibility
and restrictions, and a button bar; its ticket contract is
`RALLY_RACE_TICKET`, with shared street-race ticket paths. Reference assets
remain local inspection material, never a required launcher/runtime input.

The base image names `CShowPauseScreen` and
`CShowUIScreen_CareerStreetRaceSelect`; the Rally hub/loader/initial-unlock
behavior names were not found in its ASCII name inventory. That inventory
is evidence for the port plan, not a complete factory-dispatch proof.
Next, trace the native street-race hub and ticket constructors, implement
the Rally ticket data/selection behavior against owned event metadata, and
connect the original pause/intro/return flow. Reusing the base's native UI
components must preserve seven championships, eligibility, car selection,
unlocks and return/outpost behavior. A host settings page does not pass
this gate. Inspection receipts are under ignored
`.local/dlc/reference/original-entry-20261006/`.

### Diagnostic AI control handoff and final-stage return (2026-10-06)

The diagnostic driver now releases native AI control when its stage ends,
using the title's existing setter only for the same tracked car and race
serial. Previously its bookkeeping was cleared without restoring control.
The final-stage route now requires exactly one matching release to player
mode; its runner check rejects missing, duplicate, out-of-order and mismatched
releases. The 58 runner tests and desktop Release build pass.

Private Vulkan session `20261006T064015Z-p1964` passes the unchanged driving
and free-roam return gates: route 41 finishes in 261.547629 seconds, exactly
one stage result completes championship 7, the prior three stage times
remain intact, and the saved total is 716.665455861776 seconds. The native
AI setter returns control to the same car/serial. All 98 owned pace plays
finish on the native audio update thread. After returning through the base
loader, ordinary scripted player input moves 85.172875 metres in mode 17.
Results and return captures were inspected; all 12 pinned source hashes
match. Evidence: ignored `E:/horizon1-recomp-tests/dlc-2026-10-05/`
`rally-full-garage-final-stage-vk5/qualification.json` and `result.json`.

This qualifies the diagnostic final-stage transition and player control
handoff, not original entry/hub or manual Rally championships. Native
decrypted-save snapshot tracing was not enabled for this run; its native
garage, purchased-parts and winnings preservation are not newly audited.
Official Rally rewards/unlocks and a reload audit of this new completion
remain open.

### Native hub component probe and owned route labels (2026-10-06)

Preparation recipe 8 merges owned Tracks.str and Environments.str for all
20 languages while preserving every base label. All 40 real table pairs
and 112 targeted DLC, preparation, string, runner, release and symbol tests
pass. Original inputs and all 12 pinned save-file hashes remain unchanged.

Private Vulkan session 20261006T074850Z-p30440 renders seven display rows
through the base native street-race hub at frame 4000. This only proves
component rendering: Back remains on the hub, navigation is unqualified,
cards use street-race styling with repeated hub titles and placeholder
rewards. The private proxies use the base street-ticket style contract;
the festival-style mismatch previously dereferenced an unpopulated native
row field. No broad crash guard or production unlock was added.

Original pause/intro, ticket bindings/artwork, eligibility, car selection,
return lifecycle and Rally rewards/progression remain open. Probe hooks
require both scripted-test mode and an explicit environment flag.
Evidence: ignored D:/horizon1-recomp-tests/rally-native-hub-20261006/vk11/
qualification.json; owned-label receipt under .local/dlc/.

A second private hub probe (20261006T075643Z-p4768) adds the base blackout
and empty-screen lifecycle. Seven rows still render, but Back still retains
the activity owner. Original native input/ownership routing remains open.

The latest ARM64 APK (SHA-256 24EA9E6E3B1E1A22E7FACC195E35691640C551F479D72C0737E25DEE8E386668)
is signed, aligned, library-verified and installed on Odin bd89bfde. Private
startup sessions complete frame 1200 and shut down normally with CRLF
scripts. The actual Android screen after reload shows MSAA Off, its static
restart badge and no pending-restart note. Guest framebuffer captures omit
the host settings overlay. Normal device progress was not overwritten.
Android Rally driving/graphics/performance remain unqualified. Evidence:
D:/horizon1-recomp-tests/android-native-hub-20261006/startup-qualification.json.

### Native hub Back and free-roam control (2026-10-06)

Private probes confirm native controller Back event 95 reaches the screen
with its return action present. The minimal fixture incorrectly used
InGameUI.exit.enterForLoading for Back; normal InGameUI.exit.enter restores
the HUD and releases game control. The component fixture also removed a
blackout that had no matching intro/fade-in. Session 20261006T081213Z-p18716
renders seven rows, handles Back, returns to visible free roam and moves
4.970091 metres under scripted player throttle before the nearby barrier.
The return capture was inspected. All 12 pinned source save hashes match.
113 targeted tests and the latest desktop Release build pass.

This supersedes the earlier private Back failures. It does not qualify
original Rally entry/intro or championships: proper titles/artwork, unlocks,
eligibility, car selection, native pause integration and official
rewards/progression remain open. Navigation still needs selection evidence.
Evidence: D:/horizon1-recomp-tests/rally-native-hub-20261006/vk17/qualification.json.

Session 20261006T081425Z-p1892 additionally confirms native ticket selection
changes after D-pad right (277 to 279 to 275, wrapping under a held input),
then Back restores visible free roam and scripted throttle moves 4.839361
metres. This supersedes the earlier navigation uncertainty for the private
component fixture. Original Rally UI bindings and progression remain open.
Evidence: D:/horizon1-recomp-tests/rally-native-hub-20261006/vk18/qualification.json.

Clean structured-input logging and the latest desktop binary repeat those
gates in session 20261006T081709Z-p11300: right input selects 279/275,
Back releases ownership and throttle moves 4.959409 metres.
All 12 pinned source hashes remain unchanged. Latest evidence:
D:/horizon1-recomp-tests/rally-native-hub-20261006/vk19/qualification.json.

### Native ticket championship titles (2026-10-06)

Private session 20261006T082453Z-p27380 binds each ticket heading to its
owned championship name. The street-hub query used h.Name for every card;
the probe substitutes e.Name only in the worker-owned hub-4 query copy.
No base image string is changed. Seven rows, navigation, native Back,
free-roam ownership release, frame-4000 completion and shutdown pass.
The Clear Springs, Rockies and Red Rock headings were visually inspected.
The base CarClasses table confirms TargetClass 4 is B (not A); the Clear
Springs badge matches. All 12 pinned source save hashes are unchanged.

This supersedes the repeated-hub-title limitation for the private fixture.
Street-race header/artwork and zero rewards remain. Eligibility currently
uses base event clones; owned restrictions, car selection, original
pause/intro and championship progression remain unqualified. This is not
a production hub. Query substitution requires explicit scripted Rally
probe and DLC SQL tracing; the ordinary runner clears DLC_TRACE, so the
trace used launch-preview with an existing private state. Evidence:
D:/horizon1-recomp-tests/rally-native-hub-20261006/vk22/qualification.json.

### Correct championship and stage name assignments (2026-10-06)

The earlier private ticket probe proved string binding, but its six
incorrect championship-to-route name assignments were not qualified.
Preparation had string groups in a different order from SERIES_ROUTES.
The owned Tracks table and localized Tracks.str labels establish the
correct order: Rockies, Clear Springs, North Plains, Montano Plains,
Beaumont, Kettle Hills and Red Rock. The route sequences remain unchanged.

Recipe 9 corrects both championship and 28 stage-name references and
invalidates old prepared caches. All 560 owned label comparisons pass
(28 routes in 20 languages). A real private recipe-9 preparation verifies
all 28 resulting event labels against the owned track labels and all
seven activation prompts against the authored championship names. All
12 pinned source and 12 private save hashes match; 113 targeted tests pass.
The regression checks authored Rockies and Red Rock labels independently
of the implementation constants. No v4 file is a preparation input.
Evidence: D:/horizon1-recomp-tests/rally-labels-20261006/qualification.json
and .local/dlc/rally-route-name-qualification-20261006.json.

The existing hub display fixture still contains its old private proxy
labels until explicitly refined. Original car-selection/restriction
behavior, pause/intro, artwork and championship progression remain open.
The update/reference restriction tokens were read for comparison only;
no unsupported Rally restriction token was added to the base runtime.

### Native car selector and championship class limits (2026-10-06)

Recipe 10 assigns the correct A/S/B/A/B/S/R3 targets to all 28 stages
and copies the supported base FR06 class restriction (0x04). Older caches
rebuild. Actual preparation verifies every class/restriction row and the
unchanged base restriction. All 24 source/private save hashes match; 113
targeted tests pass. Evidence:
D:/horizon1-recomp-tests/rally-class-20261006/qualification.json.

The private native hub now opens the base CAR SELECT screen and Back
returns to the hub. A B-class fixture compiles a native performance-index
ceiling of 0.650500. A diagnostic 0x84 restriction produces exactly the
same selector predicate: the Rally upgrade flag is ignored by the base
game. The private fixture was restored to 0x04 after this comparison.
The selected Escort card and a second car card render; another card is
blank. Hub titles/classes render, but street header, black artwork and
zero-reward placeholders remain. All three runs complete frame 4000 with
five captures and normal shutdown. Evidence:
D:/horizon1-recomp-tests/rally-native-car-select-20261006/vk2/qualification.json
and its vk1/vk3 comparison receipts.

Next: port owned Rally-upgrade eligibility, qualify car confirmation and
stage loading, then integrate the original Rally entry/menu lifecycle.
These are component probes, not a production original-flow Rally hub.

### Native car confirmation exit (2026-10-06)

Selecting the Escort reaches the base upgrade recommendation prompt,
which names the selected North Plains Rally. The first test deliberately
stopped at this prompt and does not qualify cleanup. A second test uses
X Race Anyway: the diagnostic next branch closes the UI, releases the
control owner, restores the free-roam HUD and permits 5.10 m of driving.
Frame 4000, five captures and normal shutdown pass. Evidence:
D:/horizon1-recomp-tests/rally-native-car-select-20261006/confirm-vk2/qualification.json.

No stage loads in this fixture. Automatic upgrade purchase and original
Rally upgrade eligibility remain untested/unimplemented, respectively.

### Native selector to resumed stage (2026-10-06)

An explicit global.show_empty_screen before InGameUI.exit.enterForLoading
fixes the private fixture's loading stall. Earlier vk1-vk4 frame-8000
completions did not reach the career loader and are recorded as failures.
The registered base street_race_hubs.load_into_event state then loads the
current native selection without a hardcoded event name. The vk5 probe
exposed a second defect: unnamed loads bypassed the resume guard and
restarted stage one despite a saved stage-four attempt.

The shared runtime loader now resolves mapped stage-one selections before
applying its existing championship/resume guard. Native confirmation of
the Red Rock ticket (event 247, empty loader name) now loads saved route
41/event 268 with resume=1. The private vk6 test starts the race through
the base pre-race screen, drives 230.44 m with player driver type 0, and
records three native co-driver cue plays. Frame 10000, eight captures and
normal shutdown pass; all 12 pinned source save hashes remain unchanged.
Evidence: D:/horizon1-recomp-tests/rally-native-stage-select-20261006/vk6/qualification.json.

This remains a private hub component: original pause/discovery, Rally
header/artwork/prizes, upgrade eligibility and full manual championships
are incomplete. The base HUD and a floating start marshal are visible.
The production preparation still uses the existing entry flow. No APK
was rebuilt for this desktop qualification.

### Native other-championship preservation guard (2026-10-06)

A fresh recipe-10 private fixture selects Clear Springs (stage-one event
259) while Red Rock has an unfinished stage-four attempt. The unnamed
loader now rejects this selection before loading any other stage and
returns to free roam. Control releases and 5.13 m of driving pass.
The Rally progress file is byte-identical; all 12 pinned source save
hashes remain unchanged. Frame 11000, nine captures and normal shutdown
pass. Evidence: D:/horizon1-recomp-tests/rally-native-stage-select-20261006/other-series-vk4/qualification.json.

The earlier three runs pressed Right at the last ticket and retained the
Red Rock selection, so they do not qualify this guard. The native ticket
probe is still private. Original in-game retirement messaging remains
open; this guard currently returns to free roam and records a diagnostic.
The canonical ignored fixture builder now starts from recipe 10 and uses
the qualified screen-dismissal/loading chain.

### Owned ticket artwork binding (2026-10-06)

The native ticket query reads Events.EventTicket. The supported base
texture binder chooses FestivalRaces or StreetRaces from CareerEventStyle.
Prepared stages inherited FR06 ticket 043, so changing the private hub
to street style requested an unavailable street ticket and rendered black
cards. This was not caused by the cloned track IDs: owned LogoSmall paths
already reference the correct original track thumbnails.

Recipe 11 assigns RALLY_01 through RALLY_07 to the four stages in each
championship. Preparation copies the seven owned RallyTickets front
images to reserved names in both supported base-UI folders. These are
byte-identical aliases in the managed derivative; base-game tickets and
owned files remain unchanged. Old caches rebuild automatically. A real
preparation verifies all 14 image hashes, all 28 database bindings, FR06
ticket 043 unchanged, and all 24 source/private save hashes unchanged.
The 26 targeted preparation, stage-seed, import, strings and archive tests
pass. The stage-seed fixture was also brought up to date with recipe 10
class/restriction fields after the broader Rally test exposed that gap.
Evidence: D:/horizon1-recomp-tests/rally-artwork-preparation-20261006/qualification.json.

The private native carousel now displays the authored Clear Springs,
Kettle Hills and Red Rock images. Frame 4700, five captures and normal
shutdown pass. Evidence: D:/horizon1-recomp-tests/rally-native-artwork-20261006/vk1/qualification.json.
The street-race header, duplicate dynamic/baked labels, zero-reward
placeholders and original Rally scene/controller port remain unfinished.
This qualifies owned artwork resolution, not the original full UI. No
update file is a preparation/runtime input. No APK was rebuilt for this
data-only preparation change.


### Native Rally pause-entry encoder investigation (2026-10-06)

The existing eight-row scene encoder now relocates later items' companion
owners when inserting a row. Its relocation regression and stock scene
round-trip pass. This does not restore the original Rally entry yet: private
session 20261006T095550Z-p20960 served the inserted pause scene but crashed
during scaler binding initialization (pscrash-v1-125f37f5ce0b643facc6). The
prototype remains default-off; no existing menu row is repurposed for Rally.
Receipt: D:/horizon1-recomp-tests/rally-pause-relocation-20261006/qualification.json.


### Native Rally pause-entry binding follow-up (2026-10-06)

The encoder can now clone any authored row and remaps only typed string
keys in copied track/animation records. Two regressions and all seven
real-template structural checks pass. The Message Center payload is unchanged
by the string-key fix and still fails scaler initialization. A read-only
resolver probe confirms its paths exist but their values are not live objects.

Cloning the first row passes initialization and reaches private free roam
(frame 4200, session 20261006T101446Z-p18232), then crashes on the first
pause open (frame 4300): sub_82E62A10 reads a null binding on a kind-5
137ED5BA expression node. No eighth-row focus or activation passed. Resolve
expression construction/registration before enabling the native Rally entry;
keep the prototype default-off. The pinned seed profile hash is unchanged.
Evidence: D:/horizon1-recomp-tests/rally-pause-bindings-20261006/qualification.json
and all-row-encoder-checks.json. The fresh read-only GitHub inventory still
contains 27 open issues; no remote issue state or comments were changed.


### Android bloom default and qualification (2026-10-06)

Bloom now defaults off with a live Graphics toggle on desktop and Android.
The hook uses the native frame-local scale at 8246554C; it does not edit
weather data or remove the combined tone-mapping pass. Three desktop private
runs and the Odin on/off/restore run pass, with normal shutdown. Android
session 20261006T103905Z-p8506 completes frame 5400 and three free-roam
captures; all 17 normal user files and the PC pinned profile are unchanged.

This qualifies the switch and gameplay stability, not cutscenes/showroom/
photo mode, general Android graphics or a performance gain. The filter still
runs. Android paint shading and bright vegetation remain visible defects.
The original Rally pause-entry binding, hub/controller and progression gates
remain open. The latest read-only GitHub inventory still has 27 open issues.
Evidence: D:/horizon1-recomp-tests/android-bloom-20261006/qualification.json
and D:/horizon1-recomp-tests/bloom-scale-20261006/qualification.json.


### 2026-10-06: native pause companion contract

- [x] Strictly parse the pause FBF native-object records and BSG packed nodes
  and pool; consume both complete original files without changing them.
- [x] Prove that stock BGF resolves all native IDs, while the first-row clone
  has 36 missing FBF objects. Source kind-5 ID 28 is Material1583, not the
  unrelated BGF string `contract`; prior expression notes were incorrect.
- [ ] Replace blanket string-index remapping with separate native object and
  numeric geometry domains; clone independent material/texture ownership and
  coordinate BGF/FBF/BSG before enabling the Rally pause entry.
- [ ] Pass repeated eight-row pause open/focus/activation before connecting
  Rally entry. The experiment remains default-off; no live-pointer aliases
  or null-tree guards qualify the original player experience.

Validation: four companion-parser and two BGF-encoder regressions pass. Stock
FBF: version 1008, 501 objects, 106 geometry records, 71232 GPU bytes. Stock
BSG: 241 nodes, 260 pool records, exact 24488-byte consumption. Receipt:
`D:/horizon1-recomp-tests/rally-pause-companions-20261006/validation.json`.
Pinned save hash verified unchanged. Native Rally entry remains unfinished.


### 2026-10-06: coordinated native companion encoding

- [x] Encode the row's 36 independent native objects across FBF and BSG,
  separately from its 72 BGF string slots. Material/texture owners and BSG
  internal parent indexes move to their clones; immutable geometry/GPU bytes
  remain identical. All seven templates pass cross-file bounds/ID checks.
- [x] Validate literal LZX/XMem wrapping through the host archive extractor,
  including multiple 32 KiB frames, odd tails and E8 bytes. This does not
  qualify native archive delivery: both stored and LZX-wrapped stock-member
  controls stall before their first frame. An unchanged rebuilt archive works.
- [ ] Deliver all three companions through their decoded reader boundaries.
  A new script-only `scene_companions` experiment matches the whole original
  FBF at 82C7E0B0. BGF and BSG use another reader. The FBF-only run still
  constructs seven stock buttons, reaches free roam, then crashes on pause
  (pscrash-v1-89312dc6fcffd69b418f). Loose replacements are ignored.
- [ ] Qualify native eight-row pause open/focus/activation and connect Rally
  entry; no partial delivery or pointer repair counts as original-flow support.

Five companion, two BGF and three archive regressions pass. Runtime and input
preservation evidence: `D:/horizon1-recomp-tests/rally-native-companion-clone-20261006/qualification.json`.
Original UI archive and pinned save hashes are unchanged. No AppData-backed
run or device-save write occurred. GitHub refresh still lists 27 open issues;
no GitHub changes were posted. Native Rally entry remains unfinished.


### 2026-10-06: native companion delivery and binding-table fix

- [x] Deliver all three private pause companions through decoded readers: BGF/BSG at UI4 fread 82E614FC and FBF at memory-stream constructor 82C7E0B0. Whole-source matching, script-only default-off; stock resource ownership remains intact.
- [x] Fix the BGF packed maximum object ID at 0x1B. Leaving it at 763 made the native loader allocate undersized lookup/binding tables for cloned IDs 764..799. The encoder now raises it to 799; a full synthetic scene regression covers expansion and preservation of a larger ceiling. All seven templates retain valid cross-file references.
- [x] Corrected private session 20261006T120914Z-p21804 creates eight buttons and passes free roam, first pause open, four captures, frame 5460 completion and normal exit. Cloned scaler bindings resolve to live pointers.
- [ ] Register the eighth row with the native pause controller and qualify visibility, focus and activation. Captures still show seven visible rows; scrolling selects Quit and activation opens the stock Quit confirmation. Rally entry remains unfinished.
- Original-flow Rally, Android graphics/performance and the open GitHub queue remain active goals. The earlier byte-identical-reader control completed its script but its nominal pause image was still loading; it does not qualify navigation.


### 2026-10-06: eighth-row layout and native model probe

- [x] Append a private eighth data-model entry using native constructors and retained label ownership, then bind through the stock pause controller. Script-only and default-off; MAP/action 18 are probe values, not Rally entry.
- [x] Place the cloned BSG root using the seven authored rows: 53-unit Y spacing, new Y -371. All seven template structures and nine focused encoder regressions pass.
- [x] Session 20261006T122901Z-p35312 visibly renders eight distinct rows through frame 7900, completes at 8200 and exits normally. Original UI and pinned profile hashes remain unchanged.
- [x] Qualify visual focus after relocating cloned animation references into their own style-record and property-track key tables. Session 20261006T144953Z-p14844 preserves all seven stock selections, focuses the new bottom row and resumes driving after B. Twelve encoder regressions and all seven real template checks pass.
- [ ] Qualify activation lifecycle, reopen and original Rally entry. The long lifecycle route is being controlled separately; visual focus and one close/drive route do not prove native Rally integration.
- [x] Qualify B resume with all three changed companions and the eight-action model: session 20261006T140352Z-p33188 releases control, restores the HUD and drives at 42 km/h.


### 2026-10-06: live-context dispatch and native row naming

- [x] Use the SDK ExecuteTrap mechanism for injected UI calls so constructors and kernel callbacks share the live ThreadState context and restore all outer registers. Scene-only control navigates to Quit; the trap-frame run dispatches the eighth model action after seven down presses.
- [ ] Correct visual focus and qualify the full activation lifecycle. Action 18 reached its dispatcher but its unhandled path leaves the menu inactive. Existing action 17 preserves the seven stock actions and dispatches, but later captures show Difficulty UI; pause cancellation/reopen is not proved. Both runs exit normally.
- [x] Match the cloned native FBF root name to its BGF Button7 wrapper instead of retaining Button0. All seven template structures and ten focused encoder tests pass; runtime focus qualification is pending.


Correction to the action-trace interpretation above: the old trace duplicated JSON event keys. The parser hid existing callbacks. Preserving the first event discriminator proves session 20261006T122901Z-p35312 already dispatched action 18 after seven downs. The new trace calls its payload notification. ExecuteTrap aligns callback contexts but is not a proven input-freeze fix. Visual highlight remains on the first row; named-root session 20261006T125340Z-p35976 completes at frame 11500 with ten captures and normal exit, but B before activation leaves the pause scene visible. Visual focus and exit remain unfinished.

Stock-scene exit control 20261006T125751Z-p16000 uses original companions with no model append, completes at 7500 with four captures and normal shutdown, but also leaves its seven-row pause menu visible after the same delivered B press. The exit failure is shared by this scripted route; its native input/state/render cause remains open. Do not attribute it solely to the clone. The latest desktop build includes the corrected notification trace field.


Native pause/resume follow-up (2026-10-06): stock controls accept B as action 95 with a nonnull done callback at frame 7000; native pause input calls then stop. Throttle after B produces no movement. A no-pause control drives approximately 108 metres and reaches 67 km/h. Three private routes complete normally. This shared pause/resume failure remains open; trace downstream event consumption and game-control release before qualifying original Rally menus. Receipts: rally-native-companion-clone-20261006/qualification.json.


Pause experiment attribution correction (2026-10-06): earlier stock-companion controls still enabled experimental buffer substitution. Reader-control session 20261006T132609Z-p23224 clears completion events after B but retains the pause owner through frame 7500. Experiment-disabled session 20261006T133000Z-p15164 releases control by frame 7080 and driving resumes at 84 km/h. Identity-fast-path session 20261006T133343Z-p2804 makes no substitutions but still retains pause ownership. Experiment mode reproduces the failure; buffer replacement alone is not the proven cause. Unchanged companions retain native storage, with equality checked once at input loading. Path-binding/cursor detail now requires explicit UI_TRACE, permitting quiet controls. Changed companions, experiment tracing and original Rally menu integration remain unqualified.


Native pause close qualified for the cloned scene (2026-10-06): session 20261006T140352Z-p33188 substitutes all three changed companions and appends an eight-action model. Filtering native-dereferenced cursor resource lengths before host page queries removes redundant checks from unrelated tiny reads. B releases game control by frame 7080; the HUD returns and the car drives at 42 km/h. Earlier FBF memory-only identity control also passes when unrelated fread cursor inspection is skipped. Eight distinct rows remain visible, but seven downs still highlight the first MAP. Visual focus, activation lifecycle, reopen and original Rally entry remain open. Normal structural UI dumps now require explicit tracing; no frame-rate gain has been measured. Original archive and pinned seed profile hashes remain unchanged. Latest GitHub read-only refresh remains 28 open issues with no new/changed reports.


Native cloned-row focus narrowed (2026-10-06): five new list/focus sessions pass native pause close, ownership release and resumed driving. Per-down captures show correct focus on all seven stock rows; selecting model index 7 highlights the source template instead of the new bottom row. The first-row template highlights original MAP; the last-row template highlights original Quit. Eight row controllers and eight native event targets are distinct. The optional list+324 controller is null in the stock control too. The inspected root animation tracks contain no position keys; resetting root Y remains an unproven explanation. Visual binding root cause, activation/reopen and original Rally entry remain open. Read-only probes are render-test gated. Receipt: D:/horizon1-recomp-tests/rally-native-companion-clone-20261006/qualification.json. Original archive and pinned seed profile hashes pass. No Android or GitHub issue fix is claimed by these UI checks.


Native cloned-row visual focus fixed (2026-10-06): animation entries are two flag bytes and a uint16 reference. Zero in the first flag selects a style record; nonzero selects a property-track key. The encoder cloned those tables without relocating the animation entries, so the new row animated its source template. Both domains now relocate to appended copies, original animations/external references remain unchanged, and references beyond the native 14-bit capacity are rejected. Session 20261006T144953Z-p14844 shows all seven original selections correctly and the new eighth row highlighted at the bottom. B releases control and driving resumes; eleven captures, frame-7500 completion, normal shutdown and input/seed hashes pass. Twelve focused encoder tests and seven real template checks pass; all 282 cloned-root animation references bind within the new row. Descriptor-key and independent-action-string controls ruled out those aliasing hypotheses. Activation/reopen and original Rally entry remain unfinished. GitHub read-only refresh still has 28 open issues, with no new or changed reports; no public issue is claimed fixed by this prototype change.


Native prototype lifecycle control (2026-10-06): detailed-trace session 20261006T145247Z-p24620 delays pause release past its reopen schedule and does not qualify activation. Identical quiet session 20261006T145845Z-p12052 passes B resume, a second eight-row pause instance, correct new-row focus, native Difficulty activation (probe action 17), B cancellation back to pause and final B gameplay return. Ten captures, frame-11500 completion, normal shutdown and original input/seed hashes pass. This qualifies one prototype lifecycle; repeated activation, three-run stability, native AddMenuItem and original Rally entry remain open. Detailed tracing can disturb the schedule; its specific cost is not measured. This does not qualify Android graphics/performance or close a public GitHub issue.


### Native pause prototype repetition (2026-10-06)

- [x] Repeat the identical frame-11500 lifecycle route from three fresh private seed copies: 20261006T145845Z-p12052, 20261006T150641Z-p13348 and 20261006T151006Z-p37884. Each passes ten captures, two eight-row model constructions, correct focus, native Difficulty activation/cancellation, gameplay return and normal exit.
- [x] Activate the added row twice in one process with close/reopen between activations: 20261006T151333Z-p17604 passes three model constructions, fifteen captures, frame-14500 completion and exit 0. Both activations open Difficulty; both cancel to pause; both final closes restore the HUD and release control.
- [ ] Instrument native component allocation/destruction before claiming leak-free lifetime qualification. Pause owner addresses can be reused on reopen; production scene generations must advance independently of the address. Native cleanup starts at 82726320 / 82720BF8, with model cleanup at 82834600.
- [ ] Connect production callbacks and the original Rally entry/hub. MAP/action 17 remain prototype values and the experiment stays default-off.

Original archive and pinned seed hashes remain unchanged. The GitHub inventory still has 28 open issues with no changed reports; no public issue is claimed fixed by this prototype. Android graphics and sustained performance remain separately unqualified by these desktop runs. Receipts: D:/horizon1-recomp-tests/rally-native-companion-clone-20261006/qualification.json.


### Native pause lifetime qualification (2026-10-06)

- [x] Trace native pause-button construction and the deleting destructor/post-free boundary without changing guest state. The trace is opt-in, bounded and render-test-only.
- [x] Session 20261006T152422Z-p37732 accounts for three closes: 32 constructions, 24 deletions and 24 post-free returns. Each close frees all eight displayed buttons, then constructs eight standby replacements. All 73 sampled row sets match live objects; no button allocation growth is observed.
- [x] Session 20261006T153104Z-p26740 also accounts for three pause owners: each destructor sees eight model entries, clears begin/end/capacity, and reaches its native free call. Button counts and 73 live-row samples repeat the earlier result.
- [x] Both lifetime runs pass two native Difficulty activations, cancellations, gameplay returns, fifteen captures, frame-14500 completion and normal exit. Original UI archive and pinned seed profile hashes remain unchanged. These results qualify the tested pause buttons and owners/models, not every UI4 material, texture or heap allocation.
- [ ] Connect production native AddMenuItem callbacks, label ownership and scene generations, then the original Rally entry/hub. The current MAP/action-17 prototype stays default-off.

The desktop build and generated hook-symbol check pass. Lifetime receipts and captures are under D:/horizon1-recomp-tests/rally-native-companion-clone-20261006/. Android graphics/performance and original-flow Rally gameplay remain unfinished. The read-only GitHub refresh still has 28 open issues with no new or updated reports, and no public defect is claimed fixed by this prototype qualification.


### Private native menu API and caption ownership (2026-10-06)

- [x] Consume a private AddMenuItem operation for rally.entry at index 7 and construct an independent HORIZON RALLY caption through the native owned-string constructor. Verify the added model label identity before emitting the application receipt; queue admission alone is not success.
- [x] Advance native pause scene generations 1/2/3 and close each at owner destruction. Sessions 20261006T154420Z-p8668 and 20261006T155126Z-p13916 pass caption/focus, two diagnostic Difficulty activations/cancellations, gameplay return, three owner/model cleanups, unchanged button lifetime counts, fifteen captures, frame-14500 completion and exit 0. Original source/seed hashes pass.
- [x] Fix shared UI API stale-handle revival: retain the last generation after close and reject older/equal generations on reopen. Fresh generations and component IDs remain valid; closed/old handles cannot queue writes.
- [x] Enable assertions for Release host-test targets. All eleven runnable host checks pass, including UI generations, Rally progress/pace, profiles and saves. The shader-pack check is compiled but requires its separate prepared-pack fixture.
- [ ] Add the Rally activation callback and production semantic registry/completion interface, then qualify the original discovery/physical entry/hub/car-selection experience. The private caption bridge remains default-off and still uses diagnostic action 17; it does not launch Rally yet. Unicode captions and general native UI operations are not qualified by this ASCII, single-component test.

Current native receipts are under D:/horizon1-recomp-tests/rally-native-companion-clone-20261006/qualification.json. Host receipts: .local/logs/host-assert-checks-results-20261006.json. The read-only GitHub refresh still has 28 open issues with no new or updated reports; no public issue is claimed fixed by these API changes. Android graphics/performance and full original-flow Rally gameplay remain unfinished.


### Private controller Rally activation (2026-10-06)

- [x] Add a generation-specific private native HORIZON RALLY action. Successful admission takes native Resume action 3 before entering the activity; unavailable requests leave the menu open. The private controller route opens the seven-ticket native hub, returns through Back, reopens pause and repeats successfully. Two owners use separate actions 19/20 and close correctly. Adapter-disabled negative control rejects both requests safely. This supersedes the earlier private activation TODO only.
- [x] Preserve existing F6 entry. A proposed shared control-release gate and native pause callback both stalled F6 and were removed. The gate is confined to the private native-menu experiment. Final F6 session 20261006T162648Z-p36336 reaches a moving player-controlled Rally stage, with three captures, frame-4200 completion, exit 0, normal preflight, 28 installed stages, seven owned entry coordinates and both race HUD validators passing.
- [ ] Replace the private derived street-race presentation with the original Rally hub: heading, duplicate labels, prize display and Rally upgrade eligibility still need work. Finish production semantic registration, discovery and physical entry, car selection, manual championships, rewards, persistence and retirement. The new pause callback is default-off and does not qualify the complete original experience.
- [ ] Continue Android graphics/performance qualification on the Odin. No Android APK was built or installed during this native-menu work.

Receipts/captures: D:/horizon1-recomp-tests/rally-native-pause-entry-20261006/. Source profiles, original UI archive and pinned save remain preserved. Read-only GitHub inventory: .local/issue-triage/open-issues-20261006-native-entry.json (28 open, no changed reports). No public crash fix or issue closure is claimed.


### Private Rally hub heading (2026-10-06)

- [x] Replace the private hub's fixed street-race title through its native TEXT_TITLE binding. Bind the text value before copying the owned caption; free temporary native string storage after the title has its own copy. Session 20261006T163509Z-p22696 visually shows HORIZON RALLY on both openings and passes both Back returns, fresh pause generations, nine captures, frame-12500 completion and exit 0. Both bindings succeed, and original archive/source profiles/pinned-save hashes pass.
- [ ] Finish native Rally ticket presentation, prizes and upgrade eligibility. The private heading is ASCII and default-off, not localized production UI. Restore original discovery, physical entry, intro, car selection and complete manual championships/progression.

Heading captures and updated qualification.json are under D:/horizon1-recomp-tests/rally-native-pause-entry-20261006/. No Android APK was built by this change.


### Native pause, Rally ticket and car confirmation (2026-10-06)

- [x] Connect the private seven-ticket hub to the native ShowRegisterEventCarScreen. Session 20261006T164310Z-p36512 opens CAR SELECT from the native pause/Rally hub, cancels to the hub, reopens the chooser and confirms the selected Escort through the native loading path. The unnamed loader resolves ticket 247 and resumes route 41/event 268, the earned Red Rock stage-four checkpoint. The timer advances with player driver type 0; the car moves more than 160 metres between the driving captures. No diagnostic AI driver, synthetic finish or checkpoint edits are used.
- [x] Verify car chooser/cancel/reopen, both HORIZON RALLY headings and real stage driving visually. Three race HUD validators, ten captures, frame-18100 completion, exit 0 and the existing resume verifier pass. The earned Rally ledger is byte-identical to the source; source profile hashes pass. A first script attempt was rejected before game initialization for mixing a wall clock with output-frame waits. The corrected passing route uses its wall clock and validates actual race state/HUD/displacement.
- [ ] Integrate the qualified components into production-owned preparation and the original discovery/physical entry flow. Rally upgrade eligibility, blank car thumbnails, duplicate ticket labels, prize presentation/awards, intro, full manual championships and original progression remain open. This private car-confirmation fixture is default-off and does not qualify the complete original experience. Android graphics/performance work remains open; no APK was built or installed for this change.

Receipt: D:/horizon1-recomp-tests/rally-native-pause-entry-20261006/car-selection-qualification.json. Heading/native entry receipts remain in qualification.json beside it.


### Optional owned native Rally menu preparation (2026-10-06)

- [x] Add recipe 12's explicit --native-menu/--no-native-menu preparation option. Fresh states default to the existing development flow; launch preflight preserves an explicitly selected mode. The seven authored physical trigger positions stay unchanged. Sixty-five preparation/render-runner tests pass, including all seven graphs, car selection/cancel/load wiring, base inputs and source-save preservation, preflight reuse and switching the mode off.
- [x] Scope the shared native hub hooks to the current horizon_rally_01 through horizon_rally_07 activity owner. Session 20261006T170833Z-p38304 uses diagnostic activity admission only, without the private native-hub override. It opens the seven-ticket HORIZON RALLY hub focused on series four/event 265, opens CAR SELECT, cancels back to that championship and closes to gameplay. Both headings, car selector and gameplay return were visually inspected; five captures/frame-6300 completion pass.
- [x] Preserve default F6 resume with recipe 12/native_menu=false. Session 20261006T171223Z-p27420 resumes earned route 41/event 268, advances the native timer with player driver type 0, accepts throttle and moves 18.69 metres between captures. The route's preceding 30-metre movement wait, both race HUD validators, three captures/frame-4200 completion, exit 0 and unchanged earned ledger pass. Source profiles and the pinned AppData seed hashes pass.
- [ ] Qualify original physical entry. Three isolated fixtures complete without a runtime crash but do not enter the activity: the car is displaced from the authored trigger before the entry input. Native placement briefly reaches series four's x/z, then falls/resets hundreds of metres away; adding collision reset and streaming wait does not resolve it. Determine the actual ground/streaming/post-spawn lifecycle before further placement changes. Diagnostic activity admission does not qualify physical entry.
- [ ] Finish ticket labels/layout, nonzero original prizes/awards, Rally upgrade eligibility, blank thumbnail cards, introduction, full manual championships and original progression. The optional preparation mode remains experimental. Android graphics/performance work remains open; this change builds desktop only.

Receipt: D:/horizon1-recomp-tests/rally-owned-native-menu-20261006/qualification.json. Original-flow Rally completion remains false.


### Physical placement and native ground controls (2026-10-06)

- [x] Add a read-only, render-test-only PINYON_SHIFT_RALLY_GROUND_TRACE diagnostic using the native snapToGround collision query. Wait for a live presentation and parsed activities; report the current car as a positive control and all seven owned entry coordinates. Restore floating-point arguments and release the native scene reference. The diagnostic never moves cars or changes trigger fields.
- [x] Qualify the query at a normal base-game spawn: session 20261006T173021Z-p36304 returns a nonzero surface hit beneath the current car at x=-1024.605591/z=-145.869659, ground y=-9.101082. Both stationary captures, frame-2300 completion, exit 0, source profiles and pinned seed hashes pass. Remote entry-coordinate misses do not prove globally absent terrain.
- [ ] Resolve physical entry using the correct world/streaming/route and original hub context. Camera reset before collision reset/streaming does not fix the series-four placement: session 20261006T173201Z-p36580 completes six captures/frame 7200, but the car falls and resets more than 400 metres away. All eight loaded-placement collision queries miss. No activity is selected.
- [ ] Investigate the owned paused Rally hub/map flow before treating its seven markers as normal base-world driving destinations. The reference removes the player car while paused, loads a background movie and enters ShowRallyHubScreen; these behaviors are not implemented by the current base generic-activity adapter. A private track-317 ColoradoDirt world comparison, session 20261006T173607Z-p33816, also falls/resets and shows unloaded-looking grey terrain. Its eight collision queries miss, two captures/frame-2300 completion pass and physical entry remains false. Switching the world name alone is not a production fix. Original inputs, AppData and device progress remain untouched.

The first Dirt comparison preparation was rejected because patch_archive cannot add an unknown member; its launch preflight rebuilt the standard base cache, so session 20261006T173516Z-p26512 is not Dirt-world evidence. The corrected fixture changes only its private DB and existing loose activities file. All controls and limitations are recorded in D:/horizon1-recomp-tests/rally-owned-native-menu-20261006/ground-qualification.json. No Android APK was built or installed for this investigation.


The final ground-diagnostic desktop build also passes default-off F6 saved-stage
resume in session 20261006T173836Z-p33048. Route 41/event 268 advances with player
driver type 0; throttle, the movement wait, both race HUD validators, three
captures/frame-4200 completion and exit 0 pass. The earned ledger remains
byte-identical and source profile hashes pass. No entry_ground diagnostic event
is emitted with the flag unset. Driving captures were visually inspected.
The Odin 2 Portal bd89bfde remains connected; this investigation installs no APK.
The final-build result is appended to ground-qualification.json above.


### Car packs on v4 (2026-10-07)

All 21 owned packages were imported into a private copy of the v4 all-DLC
seed (`D:/horizon1-recomp-v4/seeds/v4-all-dlc-merged-2026-10-07`), each from
every local input file. Rosters come from each package's own merge database
(84 car rows; `D:/horizon1-recomp-v4/dlc-rosters/rosters.json`).

- **Licences.** The first seed held the November variant whose licence covers
  only the Gallardo offer (mask `00000002`): the native cache left the Cobra
  427, 240SX, M3 GTS and Shelby 1000 unpurchased and hidden. The importer now
  ORs the licences of verified variants with identical payloads (commit
  `efa4170`), so November becomes `FFFFFFFF` with both inputs owned.
- **Entitlements.** `v4-dlc-car-database` (the trace with `# dlc-car-ids`)
  reports all 84 rows installed, purchased and drivable; all are visible
  except the Season Pass-only Focus SVT (Rally licence `00000001` excludes
  it) and Rally's event-only duplicates, which are not selectable by design.
- **Autoshow.** The manufacturer grid lists every DLC-only make with NEW
  badges (AMC, Bowler, Cadillac, Devon, GMC, Gumpert, HUMMER, Joss,
  Koenigsegg, Pagani, RUF, Honda's additions, ...); spot-checked car lists
  show the pack cars beside base cars.
- **Purchase and persistence.** One car per pack was bought with test
  credits (cheats on, so in the separate `user-modded` save), then a fresh
  launch loaded that save, put the car in free roam and drove it: Bowler
  Nemesis EXR, Shelby Cobra 427 S/C, Gumpert Apollo Enraged, AMC Javelin AMX,
  GMC Vandura, Devon GTX, Joss JT1, Koenigsegg Agera, Honda Civic Si (1986),
  Nissan 370Z, RUF CTR2, Lamborghini Miura Concept and Shelby GT500
  Rockstar Energy. Captures were inspected
  (`D:/horizon1-recomp-v4/runs/dlc-batch{6,7,8,9,10}/verify.png`).
- **Startup cost.** With 21 packages the title merges every DLC database
  synchronously after Start: a 20.6 s main-thread stall on this machine
  (the runtime's stall watchdog logs it). Routes now wait for the merge's
  final `media\db\patch` open before the remaining title presses.

Not covered: per-car upgrades and tuning for each pack (the Rally Escort's
upgrade path is the representative qualification) and the car packs on the
base build, which were not run.
