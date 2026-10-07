# Title update v4 backlog: native Rally and 1000 Club

Status: **open**, created 2026-10-06 at `dev` `fac2230` (ShiftGlue `0038a40`),
with the Rally work in [DLC_BACKLOG.md](DLC_BACKLOG.md) still uncommitted in
the worktree. Goal: run the expansion's original native code instead of the
base-disc Rally adapter. v4 is built from the supported USA disc and the
player's own copy of the v4 title update. No update file, reconstructed image
or generated code is distributed with the project.

The base-disc build stays the default; v4 is an opt-in beside it (the
user's TU-5 decision, 2026-10-06). This
backlog replaces the premise behind the 2026-10-04 direction to keep DLC
work off v4, which assumed v4 could not be applied to this disc; it can (see
below). The Rally acceptance criteria in
[DLC_BACKLOG.md](DLC_BACKLOG.md#immediate-priority-the-original-rally-experience)
still define "done"; TU-6 is how they are met.

## Finding: v4 applies exactly to the USA disc

The preserved update (`forza-horizon-world-v4-4000d145` in
[supported-title-updates.json](../config/supported-title-updates.json)) was
built against media `4000D145`, version 0.0.0.12. The supported disc is media
`2DC7007B`, version 0.0.0.10, and no update built for it survives. Applying
the 0.0.0.12 patches to the 0.0.0.10 executables produces the exact v4
images anyway:

| Module | Pages matching v4's own hashes | Image key check | Bytes taken from the base |
| --- | ---: | --- | ---: |
| `default.xex` | 371 / 371 | pass | 20,461,989 of 24,313,856 |
| `SpeechFacade_default.xex` | 54 / 54 | pass | 2,357,463 of 3,538,944 |
| `XMediaFacade_default.xex` | 61 / 61 | pass | 2,816,906 of 3,997,696 |

**Method.** Each patch's header delta is applied to the base headers. Each
image delta is then applied to the decrypted base image while recording
whether every output byte came from the base, from patch literals, or from
zero fill. Each 64 KiB page is checked as `SHA1(page || its own descriptor)`
against the previous descriptor's digest; page 0 is checked against the
security info's section digest. That root digest comes entirely from patch
data, never from the base, so a byte copied from a differing 0.0.0.12 region
would fail its page.

**Controls.**
- All 354/36/43 base pages verify against the base's own headers.
- Flipping one bit fails exactly that page.
- The v4 image checked against the base headers fails 353 of 354 pages.
- The image-key check (`image_key_source` decrypted with the patched key
  equals the base session key) passes for all three modules.

**Identity.** The patched `default.xex` headers report media `2DC7007B` and
version 0.0.4.10, the identity the lost USA update would have produced. The
RSA signature over these hybrid headers is not valid and is not needed for
recompilation.

**Why it was ruled out before.**
- `tools/verify-fh1-title-update.py` compares the base's RSA signature with
  the patch's `digest_source`. That differs whenever the headers differ (media
  ID, version), even when the code is identical.
- The facade patches failed the SDK's key check because of an SDK bug. Their
  header delta holds several records, but `XexModule::ApplyPatch` reads only
  `info.compressed_len + 0xC` bytes of it
  ([xex_module.cpp:271](../thirdparty/shiftglue-sdk/src/system/xex_module.cpp)).
  It applies a single copy record and leaves the 0.0.0.10 key in place.
  Xenia Canary already reads the descriptor's full size.
- The earlier `.local/game/tu4-inspect/default.bin` (2026-10-04) was in
  fact the correct v4 image. It differs from the verified one only in 41
  import-table bytes that the loader rewrites.

**Evidence** (ignored, local): `.local/dlc/reference/v4-reconstruction-20261006/`.
It holds `receipt.json` (all input and output SHA-256), the
provenance-tracking LZX tool (`tool/`), `v4_reconstruct.py`, per-page results,
and the reconstructed headers and images. Verified output SHA-256:

```text
default.xex       image 74B033805AB1BCAA04DF57CD926BB2F584E74E570D7739D2552A1228F8B9DD20
                  headers 33BE0DA1544C7A7A26E5DD9E9C8DC7159489DD7CD134531EDAD4597371A250E6
SpeechFacade      image 4F86BD1BEF6C47FFDDF3A570F491684266B67BFFF6601DC9A664C1A68003EFA5
XMediaFacade      image 199D0EA9DE6C9ADFFE968EFA7B6AA90FE424193DBFAC5C2240245807D52E2F81
```

**External reports (not verified here).**
- Canary's FH1 compatibility thread,
  [game-compatibility#30](https://github.com/xenia-canary/game-compatibility/issues/30),
  reports DLC working with the update applied, and Rally crashes fixed by a
  CPU fix the project's code generator already covers.
- [xenia-canary#738](https://github.com/xenia-canary/xenia-canary/issues/738)
  shows TU4 applying to media `2B7A1346` (0.0.0.12).

## What v4 adds

v4's `default.xex` contains 102 `C`-prefixed identifiers that the base lacks
and removes none; 26 apparent removals are tail-merged strings. The v4 Rally
flows alone use **39 Rally behaviours that do not exist in the base**. The new
identifiers cover:

- **Entry and hub:** `CLoadIntoRallyFreeRoam`, `CShowUIScreen_RallyHub`,
  `CShowRallyOutpostScreen`, `CShowMultiStageEventSelectionScreen`,
  `CRemovePlayerCarWhilePaused`, `CShowBackgroundMovie`,
  `CHasSeenInitialRallyTicket`, `CSetRestrictionsForFirstRallyAutoshow`.
  v4 also adds Rally attributes to base behaviours: `onRally` on the pause
  screen and Race Central, `rallyFreeRoam`, and `applyRallyFilterByDefault`
  on car registration.
- **Race and scoring:** `CLoadIntoRallyRace`, `CRallyStageIntro`,
  `CRallyAIState`, `CRallyDriverState`, `CShowNextMultiStageLoadingScreen`,
  `CShowRallyStageScoreboard`, `CShowRallyRollupScoreboard`, `CHudStatusSplitTime`,
  `COMPONENT_CO_DRIVER`.
- **Progression:** `CInitialiseEventUnlocksRally`, `CTriggerRallyEventUnlocks`,
  `CCollectRallyUnlocks`, `CIsRallyXPEvent`, `CShowPostRaceRallyPointsScreen`,
  `CHasCompletedRallyInitialFlow`, the end-sequence and post-championship map
  behaviours, and `ACHIEVEMENT_RALLYCHAMPION`.
- **Audio:** `CCoDriverPepTalk`, `CPlayRallyChampionDialogue`,
  `CRallyPostChampMapVO`, `CWaitForVO`, `CSetNormalEQ`.
- **1000 Club and Car Challenge** (DLC-3): `CCarChallengeState`,
  `CShowCarChallengeHomeScreen` and its selection screens,
  `CHudStatusCarChallenge`, `CWaitForCarChallengeMedalAwarded`,
  `COMPONENT_MEDAL_1`…`6`. **1000 Club also needs v4.**
- **Other:** `CShowInGameDLCAlert`, `CShouldShowDLCAlertPopup`, and Auction
  House data sources (online).

The update's `media.zip` (918 files) contains:
- the Rally game flows;
- an updated `db/gamedb.slt` and `db/patch/1401000_merge.slt`;
- 113 UI4 scenes, including the Rally hub;
- official `rally.str` and `rallyupgraded.str` in every language;
- `rallyaidifficulty.xml` and `rallytracktimings.xml`;
- dust and dirt effects, and Car Challenge transforms.

Both builds already read `update:\media.zip`, and the SDK mounts `update:`
from an update data root
([runtime.cpp:325](../thirdparty/shiftglue-sdk/src/system/runtime.cpp)).
v4 needs one new import, `xam.xex` ordinal `0x69`
(`NetDll_XnpGetConfigStatus`); it is already stubbed in the SDK and Canary.
`xboxkrnl.exe` imports are unchanged.

## Review of the base-disc Rally adapter

The current Rally is not a port of the original code. Preparation recipe 12:
- clones FR06 into 28 festival events with tyre and upgrade rows;
- adds seven `horizon_rally_NN` generic activities;
- rewrites the shared festival race flow to exit through
  `CLoadIntoCareerRace("RALLY_NEXT")`;
- aliases ticket art and merges string tables.

The runtime then:
- replaces the career loader (`0x8291DD80`), the position store
  (`0x82983A90`) and four street-race hub methods;
- starts championships from the F6 page through a mailbox;
- polls race statistics into `ForzaProfile/rally-progress.toml`;
- schedules pace notes from a replacement for the native audio update
  (`0x82BB5918`).

Findings checked against the code, 2026-10-06:

| Severity | Where | Problem |
| --- | --- | --- |
| Medium-high | [prepare-fh1-rally.py `next_stage`](../tools/prepare-fh1-rally.py), [runtime hooks `PinyonShiftInstallRallySeriesLoader`](../src/pinyon_shift_runtime_hooks.cpp) | Every festival race, base ones included, now exits through `RALLY_NEXT`. The overlay mounts as soon as its files exist, but the loader hook needs a valid `rally-stage.toml`. If that mapping is empty, base races ask the base loader for a nonexistent event. Base races with Rally enabled are unqualified. |
| Medium | [rally_progress.cpp `Observe`](../src/dlc/rally_progress.cpp) | Invented championship rules. Any ended race with a reason other than 1, or a return to free roam during a stage, cancels the whole attempt. A finish counts only if two polls 12 frames apart see it. No test covers a non-success end with a series selected. |
| Medium | runtime hooks `TraceDlcAsyncQuery` | Championship ticket titles come from a SQL rewrite that is only installed in render-test plus `PINYON_SHIFT_DLC_TRACE`/`DLC_SQL_TRACE` mode, and only for the first 512 queries. Normal native-menu play shows the hub name on every ticket. |
| Medium | runtime hooks `RallyNativeHubEnabled`, [main-xex.toml](../config/rexglue/analysis/main-xex.toml) `PinyonShiftRallyNativeHubListProbe` | Despite the hook's comment, it is active whenever a `horizon_rally` activity owns game control, not only in render tests. Locked tickets are listed, the hub fields are overwritten, and the title is hard-coded ASCII "HORIZON RALLY". Native-menu mode is sticky once selected. |
| Medium | [launch-preview.ps1](../tools/launch-preview.ps1), [manage-fh1-dlc.py](../tools/manage-fh1-dlc.py) `main` | A Rally preparation failure throws and blocks all play, not only Rally. A failed preparation after enable leaves Rally enabled. |
| Medium | prepare-fh1-rally.py `prepare` | Every rebuild keeps the previous cache as `rally_adapter.previous-<uuid>` and nothing removes it. Each copy holds about 1 GB of DLC media. |
| Medium (untested) | [pinyon_shift_app.cpp](../src/pinyon_shift_app.cpp) overlay order | Mod overlays come before the Rally overlay. A mod that patches `gamedb` would hide the Rally event rows. |
| Low-medium | rally_progress.cpp `Write` | No `FlushFileBuffers` before the atomic replace. A torn ledger makes the profile's progress unreadable until it is repaired by hand. The ledger is a sidecar outside the native save transaction. |
| Low | runtime hooks hub mailbox | A retire request (value 8) would index past the seven-entry activity array at the stage selection. It is handled earlier today, so this is latent. Retire requests that arrive after the UI closes are silently dropped. |
| Low | runtime hooks pace adapter | File reads and synchronous diagnostics run on the native audio thread. The co-driver language is frozen at first use. The `0x82BB5918` replacement is installed while the audio thread may be calling through the same slot. |
| Low | runtime hooks environment gates | `PINYON_SHIFT_RALLY_BUILTIN_PROBE`, `RALLY_PROGRESS` and `RALLY_PACE_PROBE` are not tied to render-test mode, and the built-in probe skips launch verification. |
| Low | create-rally-stage-seed.py, manage-fh1-dlc.py, fh1_archive_extract.cpp | Text is read and written without `encoding="utf-8"`. The lock file grows one byte per call. The extractor uses narrow-character paths. |
| Low now, high for v4 | runtime hooks Rally section | 46 unique guest-address literals; only 2 are registered in [fh1_symbols.inc](../src/mod/fh1_symbols.inc). |

The physical-entry investigation (DLC_BACKLOG.md, 2026-10-06) is probably aimed
at the wrong target. In v4, Rally free roam is a menu hub: world presentation
off, player car removed, background movie. The seven activation coordinates
look like map pins for the unlock flow, not places to drive to.

**Still useful with v4:**
- the DLC import, ownership and licence checks (`manage-fh1-dlc.py`);
- the verified-input and atomic-cache pattern of `prepare`;
- the launch gate and its exit code;
- the control-owner and loader-idle readiness checks;
- the UI API scene generations;
- the upgrade-view and tyre-record recovery hooks, after remapping;
- the render-test harness and its Rally gates;
- the progress-ledger reader, as a one-time import if one is wanted. Routes
  are keyed by route ID; anything tied to cloned event IDs 247–274 does not
  carry over.

**Obsolete with v4:**
- the F6 Rally page and retire dialog;
- event cloning, generic activities and hub 4;
- the `RALLY_NEXT` flow rewrite and `RallySeriesLoader`;
- `RallyStoreRestorePosition`;
- the hub wrappers, list probe and SQL title rewrite;
- the entry-position hook;
- `rally-progress.toml`;
- the host pace-note scheduler and HUD;
- the hand-written upgrade data and string merges, which v4 ships officially.

Keep `kSeriesRoutes` and the route-name tables as test oracles.

## Xenia Canary comparison

Local checkout `references/upstream/xenia-canary` (`22d91c86`, 2026-07-10),
plus current `canary_experimental` sources. FH1 mounts DLC through
`XamContentCreateEnumerator` → `XamEnumerate` → `XamContentCreateEx`
(OPEN_EXISTING). It ORs the returned licence mask into the
`media\<hex>.puboffer` offer. The SDK already returns the imported mask, so
ownership needs no Canary change.

**Port (TU-1, TU-8):**
- `ApplyPatch`: use the descriptor size for the header delta. Handle a patch
  that changes the module base address by reallocating and copying the image.
- From upstream rexglue: a default-off `xex_apply_patches` switch and the
  codegen `patched_file_path` option. Today the SDK silently applies any
  `.xexp` beside an XEX, so a stray v4 file would break the base build.
- Load the DLC `spa.bin` when content opens (`ContentManager::UpdateSpaData`)
  and register its achievements through the SDK's `AchievementManager`. The
  SDK reads achievements only from the base XEX and drops unknown IDs. The
  Rally `spa.bin` holds a 60-entry table (IDs 155–215); 1000 Club's holds 70
  (IDs up to 225).
- Headless `XamShowMarketplaceUI`, `XamShowMarketplaceUIEx` and
  `XamShowMarketplaceDownloadItemsUI` through `xeXamDispatchHeadless`. Today
  they are bare stubs: no XN_SYS_UI notification, no overlapped completion,
  r3 unchanged, so a "buy DLC" prompt can hang. Never grant licences from
  them.
- Mount Marketplace content (`00000002`) read-only (the behaviour of Canary
  `b11458e49`, not its code).
- Optional: refuse a content mount over an existing symbolic link such as
  `game:` or `update:` (`9bfaff504`). Also optional: honour `kExcludeCommon`
  and de-duplicate in the enumerator (`f88bfbe41`).

**Do not port:**
- Canary's direct STFS mounting. From code reading, it loses or rewrites the
  imported licence mask.
- The `license_mask` cvar OR, which would grant the season-pass Focus that
  Rally's mask `00000001` excludes.
- The new 0x1000-byte header format and `XamContentFlush` header rewrites.
- Canary's TU signature defaults, and its quirk of treating `ApplyPatch` code
  7 as success.
- `30ac9d7` (`stvlx`/`stvrx`): the code generator already stores these
  byte-wise.

## Plan

Sizes: S ≤ 1 day, M ≤ 1 week, L > 1 week of focused work.

### TU-0: evidence and decision — S

- [x] Reconstruct all three v4 modules from the 0.0.0.10 disc and verify every
  page against v4's hash chain, with negative controls (above).
- [x] Inventory v4's native behaviours, media and imports.
- [x] Review the base-disc adapter and Xenia Canary's DLC/TU handling.
- [x] Record the plan here and link it from the DLC backlog (2026-10-06).

### TU-1: SDK patch application — S

Depends on TU-0.

- [x] Port Canary's header-size fix (SDK `17f3018`). The delta is bounded by
  the descriptor size minus its leading fields; Canary's full `size` reads
  0x4C bytes past the end. A patch that moves the load address is refused
  (error 10) rather than relocated: generated code targets one fixed
  address, and no FH1 patch moves it. Through the SDK loader, all three
  patches reproduce the pinned images and headers byte for byte, and a
  mismatched module pairing is rejected. That real-input check (the
  verifier below) stands in for a synthetic delta test; the SDK has no LZX
  encoder to build one.
- [x] Default-off `xex_apply_patches` (as in upstream rexglue). With it off, a
  module's `.xexp` is ignored with a warning and the base image loads
  unchanged (all three modules checked). Ignoring was chosen over refusing to
  start: the base build runs correctly either way. The SDK also finds a patch
  on `update:` (where the console mounts title updates), and no longer looks
  for patches of patch files.
- [x] Verification tooling: the archive extractor's `--title-update-image`
  applies one patch through the SDK and writes the headers and image before
  imports are resolved. `verify-fh1-title-update.py` checks every page against
  the patched hash chain (unit-tested with synthetic chains, single-bit and
  descriptor corruption). The provenance-tracking LZX tool remains analysis
  evidence in `.local/dlc/reference/v4-reconstruction-20261006/tool/`.

**Done when:** the SDK applies all three v4 patches to the 0.0.0.10 disc,
producing the pinned image hashes above, and the base build is unaffected.
Met 2026-10-06.

### TU-2: inputs, verification and setup — M

Depends on TU-1.

- [x] `verify-fh1-title-update.py` applies each patch and reports per-page
  verification; signature fields are now informational
  (`built_for_this_base`). `supported-title-updates.json` pins the verified
  USA image and header hashes under `verified_bases`. The real package
  reports 371/371, 54/54 and 61/61 pages with pinned image matches.
- [x] Let the launcher import the player's own update package (raw or ZIP).
  Verify its package and member hashes, store it under the existing state
  root, and show whether a v4 build is possible. Never modify the disc or
  package, and never upload or distribute them. The command-line step
  exists: `--install <state-root>` publishes the verified files atomically
  into `<state>/title-update-v4` (unit-tested: reuse, replacement keeping
  `.previous-<n>`, failed copy publishes nothing).
  `tools/launch-preview.ps1 -TitleUpdateV4` runs the v4 build. It requires
  those four verified files, skips the base-disc Rally preparation and warns
  that v4 saves are one-way. The launcher's DLC panel now has an "FH1 title
  update v4" row with "Import update" (file or folder) and "Use v4" / "Use
  base disc". It calls `tools/manage-title-update.ps1`
  (status/import/enable/disable/restore, choice stored in
  `<state>/config/title-update.json`). Enabling asks for confirmation of the
  one-way save risk. On start, the launcher builds v4 with
  `tools/build-v4.ps1` if needed and passes `-TitleUpdateV4`, which backs up
  the profile with `tools/title-update-profile.py` before the first v4 load.
  Switching back offers to restore the pre-v4 profile; v4 saves are moved
  to `backups/v4-saves/`, never deleted. If the status query fails, the
  launcher starts the base build. `check-launcher.py` passes at 940 and 1080
  wide, and the module flow was exercised on a private state.
- [x] Separate directories: `.local/game/v4-codegen` (base XEX copies beside
  their `.xexp`), `.local/generated-v4`, build preset `win-amd64-v4`,
  `codegen-v4.log`, `fh1_symbols_v4.inc`, and the runtime update root
  `<state>/title-update-v4`. The base build keeps mounting `<state>/update`,
  so it can never load v4's `media.zip`.

**Done when:** a fresh setup from the disc plus the owned update reproduces
the verified v4 images. Wrong, damaged or missing updates give a recoverable
message.

### TU-3: v4 code generation and address port — L

Depends on TU-1 and TU-2.

- [x] `config/rexglue/pinyon_shift_v4_manifest.toml` generates from
  `.local/game/v4-codegen` with `--xex_apply_patches=true`. CMake option
  `PINYON_SHIFT_TITLE_UPDATE_V4` (preset `win-amd64-v4`) selects it, passes
  the flag and defines `PINYON_SHIFT_TITLE_UPDATE_V4=1`. Generation writes
  695 files with no `REX_FATAL` stub.
- [x] `tools/port-fh1-v4-analysis.py` writes `config/rexglue/analysis-v4/`
  from the base files (comments kept, unmapped entries commented out and
  failing the run), using `tools/map-fh1-v4-addresses.py`. Methods, in
  order:
  - exact normalized function bodies (27,556 of 57,127 functions);
  - call-graph anchoring iterated through aligned code (5,561 more);
  - context windows that must cover the address and the following
    instructions;
  - vtable slots and lis/addi references, tried first for code outside
    .pdata;
  - field-offset-tolerant ("shape") context.
  Every result must shape-match over its own range. Direct branches must also
  reach the mapped counterparts of their targets: masked branches made runs of
  `subi r3,r3,4; b` thunks look identical, and an earlier version shifted them
  by one. All 123 hooks, 116 function entries, `setjmp`/`longjmp` and
  `rexcrt` map, with 4 reviewed overrides in `analysis-v4/overrides.toml`. Four
  vcall thunks have no one-to-one counterpart because vtable slots moved. They
  are covered by declaring every v4 virtual-call thunk outside .pdata (253
  added); the same rule finds 66 of the base's 70 hand-listed thunks, with
  identical sizes.
- [x] Host code: the 133 guest-address uses in `src/` (88 unique, in
  `pinyon_shift_runtime_hooks.cpp`, `cheats_map.cpp` and
  `dlc_treasure_map.cpp`) are written as `FH1_ADDR(0x…)`
  ([fh1_guest_address.h](../src/fh1_guest_address.h)). A v4 build translates
  them at compile time through `src/fh1_v4_addresses.inc`
  (`tools/generate-fh1-v4-addresses.py`, 83 verified pairs). An unmapped
  address fails to compile. The base-only Rally hub adapter's three addresses
  use `FH1_BASE_ONLY_ADDR` (0 in v4), and the adapter is disabled in v4
  builds. `tools/generate-fh1-symbols.py --v4` writes
  `src/mod/fh1_symbols_v4.inc`; `content.mount_marketplace` needed an
  override, since v4 rewrote it (0x3E8 → 0x4E4 bytes). The base table was
  also stale (two trace hooks) and has been regenerated.
- [x] Facades: both analysis files map; both keep their 14 export ordinals,
  and every v4 export points at the mapped counterpart of its base function.
- [x] `tools/tests/test_v4_mapping.py` (8 tests, synthetic PE images)
  covers:
  - normalization and shape masking;
  - exact, anchored and aligned mapping across inserted code;
  - rejection of a branch-shifted thunk;
  - vcall-thunk discovery and lis/addi reference decoding;
  - the porter's rewriting, comment keeping, `UNMAPPED` marking and override
    precedence.
- [x] `config/rexglue/accepted-codegen-warnings-v4.json` accepts the base's
  three warnings at their v4 addresses; the v4 log passes it. One new
  failure was fixed: in new v4 function `sub_827611D8`, an `lfd` separates
  the jump-table bound from its branch, so the analyzer read past ten entries
  and merged the next function. An explicit `[[switch_tables]]` entry in
  `analysis-v4/v4-additions.toml` fixes it.

**v4 differences that host code must respect** (found while porting):
- Pause actions after 5 shift by one: v4 inserts a new case 6, likely Rally.
  The base MULTIPLAYER/SETTINGS case 6 is v4 case 7.
- Input action IDs shift: resume actions 95/103 are 96/104 in v4.
- Classes grew: for example the pause object field 0xD48 is 0xD68, and
  front-end state 0x168/0x179 are 0x16C/0x17D.
- Struct offsets used by host code and the mod offset table therefore need
  per-feature review (TU-4); `fh1_symbols_v4.inc` marks every offset
  unverified.

**Done when:** the v4 build compiles with every hook resolved by a recorded
mapping, none disabled to make it build, and the base build is unchanged.

### TU-4: v4 runtime, media and saves — M

Depends on TU-3.

- [x] Mount the update's `media.zip` through `update:` and confirm the game
  prefers it over the disc's copies. Recheck the archive tools and overlay
  ordering for update media, and drop preparation steps whose data v4 ships.
  The title's own loader opens `game:\update\media.zip`, then
  `update:\media.zip` (strings at image offset 0x1378C, identical in base
  and v4), and v4 mounts `<state>/title-update-v4` as `update:`. The archive
  has 918 members: 795 not on the disc (Rally and 1000 Club flows,
  `rallyupgraded.str`, `carchallenges/`, `db/patch/1401000_merge.slt`) and
  123 replacing disc files (`db/gamedb.slt` among them). v4 runs use them:
  the native Rally loading screen, intro and mode 20 come from
  `game_rally_*_flow.xml`, and v4's `gamedb.slt` already holds the Rally
  cars the base disc lacks. `launch-preview.ps1 -TitleUpdateV4` skips the
  base-disc Rally preparation, and the base build mounts `<state>/update`,
  which never holds v4 media.
- [x] Qualify the native renderer's shader packs, Vulkan pipeline cache and
  native hooks on v4. Recapture shaders where v4 or its media differ.
  Both builds look up the same pack key
  (`4D5309C9.fh1-native-v3.vulkan.2A8D70DB.08.1x1.pnsp`); the update ships
  no shaders. `fh1-map` from a seed carrying the player's Vulkan shader
  storage (`v4-vkcache-2026-09-27`, `--seed-vulkan-shader-storage`)
  recreates 825 of 825 stored pipelines on both builds and renders the same
  free-roam frame. v4 translated 163 shaders the base run did not (930
  common, none base-only); they are translated on first use and stored,
  so no recapture or new pack is needed.
- [x] Measure profile compatibility on private copies only. Check whether v4
  rewrites `ForzaProfile`/`VersionFlags` in a form the base build cannot read,
  and back up before any first v4 load. Never let a v4 run touch the AppData
  save. Measured in TU-5: v4 loads base saves unchanged, but a v4-written
  `VersionFlags` (`00000004 00000002` after `cmss`) leaves the base build on
  PRESS START. `launch-preview.ps1 -TitleUpdateV4` backs up every profile
  to `<state>/backups/pre-v4/<stamp>` before the first v4 start
  (`tools/title-update-profile.py`, unit-tested), and the launcher offers
  the restore when switching back (TU-2). Every v4 run used private seed
  copies.
- [x] Re-qualify settings, cheats, the UI API, photo export, save backups,
  the Treasure Map restoration, achievements and mods against v4 addresses.
  Offsets known so far (from aligned instructions of matched functions):
  - **Car class:** the native AI-control setter (base `sub_8249E570`, v4
    `sub_8250B050`) reads +0x3B80/+0x3B88 where the base reads
    +0x3B70/+0x3B78, so the player-car fields after about 0x3B00 moved by 16.
  - **Race statistics:** base `sub_8262B348` → v4 `sub_826D3068` uses
    +0x368/+0x36C instead of +0x360/+0x364.
  - **Pause object:** 0xD48 → 0xD68.
  - **Unchanged:** the vehicle-pose fields (1500, 15120, 15184; stride 1056)
    and the main-loop delta (0x1C0).
  - **Mod offset table, verified field by field:** 33 of 34 offsets are
    unchanged and `profile.loaded` moves 40 → 44. The evidence is
    `profile.add_value` 824F285C → 8255E5C4, `lbz 40(r3)` → `lbz 44(r3)`,
    with words confirmed in both images. The collectible record's revealed
    setter is still `stb r4,40(r3)` (v4 82C65210), and `game.user` (108)
    and `flyer.state` (148) are unchanged at every site where the object
    type is proven. The earlier 108 → 112 and 148 → 180 changes belong to
    other objects. `config/mod/fh1-offsets-v4.toml` records each value with
    one base → v4 site; `generate-fh1-symbols.py --v4` requires every offset
    to be listed there and marks it "verified on v4". `fh1-mods-ui` still
    passes on the rebuilt v4 build.
  The base-disc Rally adapter, which reads the car and race-statistics
  fields, is disabled in v4 builds. Any v4 diagnostic driver must use the v4
  offsets.
  Re-qualified on v4 so far:
  - **Settings:** `v4-settings-gate` (a copy of `fh1-settings-gate`) passes
    `check-fh1-settings-gate.py`: 103 F6 opens and closes, keyboard, pad and
    mouse navigation, input returned and the car driving. The copy differs
    only after the closing click. That click passes through to the native
    pause menu in base too, but in v4 it lands on row 2, HORIZON RALLY, and
    opens the unowned-content notice, which needs A before B resumes.
  - **Treasure Map:** reveals 172 of 287 activities on v4 (148 before).
  - **Save backups:** written at session start and on save.
  - **Exit 0 is not qualification here:** `fh1-photo-mode`,
    `fh1-trainer-collectibles`, `fh1-collectibles`, `fh1-treasure-map` and
    `fh1-mods` all exit 0 on v4, but their captures show otherwise:
    - photo mode stops on SETTINGS, because the scenario steps rows by
      position and v4 adds a row (`v4-photo-mode` copy queued);
    - trainer collectibles' "map-on" capture is free roam, but the base build
      captures the same frame, so the scenario has drifted on both builds
      (no v4 regression; cheat events match);
    - the treasure map's owned-map capture matches the base build's capture
      of the same scenario (this seed already owns the map);
    - the v4 seed has no mods installed.
    Any scenario that navigates the pause menu by position needs a v4 copy.
  - **Photo mode:** `v4-photo-mode` (three rows down) reaches the photo
    camera with its pitch/yaw HUD and controls. Its only failure is the same
    extra v4 load hitch in the simulation-delta gate (3, limit 2).
  - **UI API and host features:** `fh1-host-features` (achievement toast
    and list, controller remap, Settings → Profile → Save backups → Restore)
    follows the same host-UI screens and events on v4 as on base. v4 writes
    one extra save backup, consistent with v4 upgrading the profile on its
    first save.
  - **Achievements:** the achievements dialog opens on v4. v4's XDBF has 60
    (Rally included) and 1000 Club adds 10 through its `spa.bin` (TU-8);
    unlocking them needs TU-6 and TU-7 play.
  - **Address audit:** every guest address in `src/` is wrapped in
    `FH1_ADDR`/`FH1_BASE_ONLY_ADDR`, except comments, the 0x82000000 and
    0x83000000 range bounds, and v4-only code.
  - **Mods:** base-targeted mods were correctly rejected ("made for another
    game executable"): the v4 build identifies as `74B033805AB1BCAA`.
    `game_version` may now list several builds (`mod_host.cpp`, MODDING.md),
    and both samples list both. On a v4 seed with both installed,
    `hello_telemetry` loads and launches through the v4 symbol table, and
    `english_strings` overrides `en.zip`. The base build still loads both
    list-form manifests. `fh1-mods-ui` gives the same mod events on both
    builds (both mods loaded, `en.zip` override, the dialog, the "Show
    telemetry" menu action, the `PauseMenu.str` string). The pause menu
    shows the mod's relabelled row "PHOTO MODE (F8 SAVES A PNG)" on v4's
    menu. v4 also tags a save with the mod set, because v4 saves the
    upgraded profile. The HUD label is a host overlay, which guest
    captures omit on both builds.

**Done when:** v4 starts from a fresh profile and a pinned seed copy with
media mounted, and the save behaviour is documented before any player-facing
switch.

### TU-5: baseline qualification on v4 — M

Depends on TU-4.

- [x] On Vulkan, run title screen, opening drive, free roam, a race,
  save/reload and exit. Use the existing render-test routes with v4 seeds,
  plus one visible manual pass. Manual pass 2026-10-07 by the user,
  `launch-preview.ps1 -TitleUpdateV4` on a private copy of the 1000 Club
  seed (`D:/horizon1-recomp-v4/play/manual-2026-10-07`): free roam, map,
  photo mode and settings "working great". The profile was backed up to
  `backups/pre-v4` first, and every session ended through a normal window
  close with exit code 0.
- [x] Compare frame time against the base build on the reference desktop and
  record any regression. Keep a working base build throughout.
- [x] Decide which build the launcher uses by default, and record the user's
  decision here. **Decision (user, 2026-10-06): base stays the default and
  v4 is an opt-in beside it**, with a profile backup before the first v4
  load and a restore path back to base (TU-2).

**Done when:** v4 passes the base gates with no Rally content involved.

Progress 2026-10-06, Vulkan, hidden, private copies of
`D:/horizon1-recomp-v4/seeds/v4-appdata-2026-09-27` (the pinned AppData seed
plus the verified update installed by `--install`):
- `fh1-smoke` passes: the v4 title screen renders.
- Fresh profile: `fh1-opening-sync --fresh-profile` from a seed with no
  profile (`v4-fresh-2026-10-07`: config, cache and the verified update
  only) passes PRESS START and the single-player menu, then plays the
  new-player opening drive in mode 17 (yellow Viper, Bass Arena radio,
  "PRESS RT TO ACCELERATE").
- `fh1-map` passes (new v4 baseline recorded). The base 0.0.0.10 save loads
  unchanged in v4: Mazda MX-5, 167,700 credits, Collect Blue Wristband.
  Free roam, the map and the return all render.
- `fh1-pause` renders v4's native pause menu: MAP, HORIZON RALLY, SETTINGS
  (our relabel works on v4's case 7), PHOTO MODE, MESSAGE CENTER, SPONSOR
  CHALLENGES, MY PROFILE, QUIT. It fails only the simulation-delta gate (3
  invalid deltas, limit 2) at an unchanged hook site, so the extra entry is a
  v4 load hitch; the gate needs a per-build limit.
- First boots exposed unregistered indirect-call targets (82E55C00,
  83171338). These are fixed by `analysis-v4/v4-additions.toml` and
  `tools/find-fh1-missing-thunks.py` (35 declared functions in all).
- Race: `fh1-race-start-wait` enters the 8-car Recaro event. Its
  `vehicle-moved` wait was met during v4's slower grid placement, so its
  captures landed on the countdown. A v4 copy that waits later
  (`v4-race-start-wait`) shows the race running: 00:10.376 on the clock,
  114 km/h, AI ahead.
- Save/reload: `fh1-race-retire` writes `ForzaProfile`, `PlayerDatabase`,
  `VersionFlags` and a new empty `NeedsAA`. A fresh v4 process reloads that
  state through `fh1-map` (Mazda, 167,700 credits).
- **A v4-written save is one-way.** `VersionFlags` goes from zeros to
  `00000004 00000002` after the `cmss` tag, and the base build then re-reads
  it in a loop and stays on PRESS START. A player-facing switch must back up
  the pre-v4 profile and restore it, never edit it, to return to the base
  build.
- The vehicle-pose hook's offsets (active slot 1500, position 15120, forward
  15184, slot stride 1056) are unchanged: the v4 function is
  instruction-identical at those fields.
- Every run so far shuts down normally.
- Frame time, `fh1-map` from the same pinned seed, hidden (120 Hz vblank
  cap, single runs): base median 8.27 ms over 2,212 frames, v4 8.28 ms over
  2,284. In free roam (frames 400–900) the medians are 8.24 and 8.30 ms,
  with p95 8.83 and 9.64 ms. No regression is visible at the cap. An
  uncapped, interleaved A/B is still needed before any performance claim.

### TU-6: native Rally — L

Depends on TU-5 and the DLC import in DLC-1.

- [x] Enable the verified Rally package on v4 without the base adapter's
  preparation. Confirm native mounting, the database merge, ownership mask
  `00000001` and the excluded season-pass Focus. `v4-rally-car-database`
  (a trace-only copy of `fh1-rally-car-database`, marker `# dlc-car-trace`)
  reads the native entitlement cache and car rows from v4 free roam. The
  content manager grew in v4 (category table +124 → +140, entitlement
  vector +180 → +204, from both builds' manager dumps). The result matches
  the base build exactly: 27 entitlements, the Focus SVT (346) installed
  but not purchased or visible, the five Rally cars and 1517 purchased and
  selectable, and all 16 car rows with the base build's upgrade counts. Row
  346 exists only in the Rally merge (`1600000_merge.slt`), not in v4's
  `gamedb.slt`, so the merge ran. The package header records licence mask
  `00000001`.
- [ ] Qualify the original flow (the manual run below covers entry, the
  intro, the hub, car selection and one championship; the remaining
  championships, stages and the end sequence are open coverage, not a
  known failure):
  - pause `onRally`, then `CLoadIntoRallyFreeRoam` and the Rally hub;
  - the first-ticket intro and initial unlocks;
  - car selection with the native Rally filter;
  - the seven championships and their 28 stages, with stage intros,
    co-driver calls and split times;
  - scoreboards and the points screen;
  - unlocks, XP, the end sequence and the champion dialogue;
  - outpost and return to free roam.
- [x] Complete DLC_BACKLOG's manual acceptance run on v4. Start in free roam,
  enter Rally through the game's own flow, finish a championship with player
  controls, receive its rewards, reload and continue, without F6 or diagnostic
  driving. Played by the user on 2026-10-07 in the same session: Rally entry
  from the pause menu, the intro stage, the hub, car selection, a
  championship with rewards, and progress kept on the next launch, all
  reported "working great". The native Rally achievements 206 (0xCE) and
  208 (0xD0) unlocked through v4's own XDBF.
- [x] Decide what happens to existing `rally-progress.toml` ledgers: ignore,
  import the stage best times, or show them only. Never fabricate native
  progress. **Decision: ignore on v4.** Native Rally progress lives in the
  v4 profile; a ledger records adapter results the native game never
  produced, so importing even best times would fabricate progress. v4
  never reads the ledgers (the adapter is compiled out), and they stay on
  disk for the base build, which remains the default.

**Done when:** DLC_BACKLOG's immediate-priority Rally criteria pass on v4.

Progress 2026-10-06. The private seed
`D:/horizon1-recomp-v4/seeds/v4-rally-appdata-2026-09-27` has the verified
Rally import, enabled with `manage-fh1-dlc.set_enabled`. No base-disc
preparation, overlay or F6 entry is involved.
- v4 mounts the package natively (`DLCRoot0:\media\dlczips\1600_pri_65`).
- Selecting **HORIZON RALLY** in the pause menu shows the original prompt:
  "Are you sure you want to quit Horizon Single Player and enter Horizon
  Rally?" (`v4-rally-enter` probe).
- Confirming with A loads through v4's Rally loading screen ("RALLY
  UPGRADES… Please wait"), plays the in-car intro, and starts the first-run
  Rally stage. The player drives a Subaru WRX on ColoradoDirt with the
  progress HUD (20–22%) and v4's own co-driver turn icon, at 53 km/h
  (`v4-rally-confirm` probe; captures reviewed).
- The probe gives no steering input, so the car leaves the road. This
  qualifies native entry and stage start only; the full stage, the hub and
  the progression checks below remain. Scenarios and captures are under
  ignored `D:/horizon1-recomp-v4/`.
- Native Rally stages run in a new game mode, **20** (festival races are 3,
  free roam 17). The v4 render-test task reports it, and with
  `--fh1_render_test_rally_ai_driver=true` it hands the player car to the
  title's AI through the native setter (base `sub_8249E570` → v4
  `sub_8250B050`). That mapping is verified: identical code apart from the
  moved field, and every base caller maps to a v4 caller.
- Engaging the AI during v4's scripted first-run intro conflicts with the
  intro's own control. With it, the car stopped at 19%; without it, the
  intro drove at 53 km/h. One such run also showed a purple colour cast
  that a no-AI run never did. A later variant engages only after about 10 s
  of mode 20 and only when the v4 control field (+0x3B88) reports player
  control. The field was already 0 three seconds into the stage, and the car
  still ended in the trees at 22%, as without the AI. The native AI does not
  drive this first-run stage. Do not use diagnostic AI for it. Manual
  driving remains the acceptance gate (DLC_BACKLOG), so the full stage, hub,
  rewards and progression need a manual run.

### TU-7: native 1000 Club and DLC achievements — M

Depends on TU-5 and TU-8's `spa.bin` work.

- [x] Qualify Car Challenge discovery, the home and selection screens, medals
  and per-car totals, and persistence with the verified 1000 Club package
  (DLC-3). Played by the user on 2026-10-07 with the default-off probe
  (`--pinyon_shift_car_challenge_gate_probe=true
  --xam_report_live_signin=true`). After the save fix below, completed goals
  stay completed through events and screen changes and survive a restart. Progress 2026-10-06, seed `v4-club-appdata-2026-09-27` (Rally
  plus 1000 Club enabled):
  - v4's pause menu adds a native **1000 CLUB** row above HORIZON RALLY.
  - Selecting it shows the game's own gate: "NO NETWORK ACCESS: This option
    is not available because you are not signed into Xbox LIVE." Dismissing
    it returns cleanly to free roam.
  - The SDK reports every profile as signed in locally (`signin_state()`
    returns 1). With the new default-off `--xam_report_live_signin=true`
    (diagnostic, private run) the gate moves to the next check: "FEATURE
    UNAVAILABLE: The Forza Horizon server is not available at this time."
  - 1000 Club is implemented as `Network::FreeRoamChallenges`
    (`CFreeRoamChallengeCoordinator`; skills, distance, A-to-B and
    speed-camera challenge types). It needs the Forza Horizon service, not
    just a sign-in flag. Offline support would need the challenge
    coordinator's server requests traced and either served from the owned
    package's data or bypassed. Investigate that before promising any
    offline 1000 Club support.
  - The gates are traced. v4's 1000 CLUB pause action (case 19 of
    `sub_827EBEE0`) checks LIVE with `sub_824CB900` (failure:
    `sub_827EAC98`) and the server with `sub_824D2090` (failure:
    `sub_82753478(menu, 4, 20)`), then opens the screen through
    `sub_82EAA148`. The default-off v4 diagnostic
    `--pinyon_shift_car_challenge_gate_probe=true` passes both, via
    mid-function hooks in `analysis-v4/v4-additions.toml` and an override of
    `sub_824D2090`. With it, **the native 1000 Club home screen opens**: the
    challenge card, car cards and achievement progress 0/1.
  - Inside the screen a second LIVE check fires; with
    `--xam_report_live_signin=true` it is followed by "The Forza Horizon
    server is not available" again, even with `sub_824D2090` overridden.
    Dismissing it returns to the pause menu. The screen evidently needs real
    service responses (challenge or leaderboard data). Offline support
    therefore means identifying those requests and serving them locally,
    which is protocol work, not a flag.
  - Scoping for that work (2026-10-07). The challenge content is local: the
    1000 Club package ships 218 loose `carchallenges/carchallenges_<car>.xml`
    files (pass/fail rules, HUD and string IDs per car) plus 271 textures,
    and the update ships `carchallenges/named_transforms.xml` and the
    `car_challenge_*` menus. The service contact happens at boot, before the
    pause menu: `XamXStudioRequest` ids 1, 4099 and 769 from 0x82B94BB8,
    0x82B920BC and 0x82B99C9C, followed by `NetDll_socket`. v4's pause
    switch has a second 1000 Club path (around 0x827EC224) whose server
    check is `sub_824127B8`, not `sub_824D2090`, and the in-screen failure
    is a third check. The likely route is to make the boot-time XStudio
    session report success and trace which challenge or leaderboard
    responses the home screen then waits for. Leaderboards cannot be
    reproduced; the challenge state must come from the local XML and the
    profile.
  - **Offline path found (2026-10-07).** `sub_824D2090` only wraps
    `sub_824127B8(service)`, the real "server available" check. It reads
    the network service at `[0x833CABB0]`: available when (`+9012 == 2`
    or `+13276`) and `+13205`. 64 call sites call it directly, so the old
    dispatcher override never reached them. A default-off codegen hook at
    its entry (`PinyonShiftServerAvailableProbe`, `return_on_true`,
    `analysis-v4/v4-additions.toml`) answers yes for every caller when
    `--pinyon_shift_car_challenge_gate_probe=true`. With that and
    `--xam_report_live_signin=true` (`v4-club-explore`, `v4-club-begin`
    under `D:/horizon1-recomp-v4/scenarios`), the native flow works
    without any server:
    - the 1000 Club tutorial ("Welcome to the 1000 CLUB Screen!");
    - the home card with achievement progress 0/1;
    - "My First Challenge" opens the eligible-car list, "EARN YOUR FIRST
      MEDAL", with the MX-5's five challenges from the local XML: Near
      Misses, Smash Signs, Speed Zone, Timed Road Trip and Carson Street
      Race;
    - SELECT ACTION → BEGIN CHALLENGES IN THIS CAR returns to free roam
      with the challenge prompts ("PRESS … TO VIEW CAR CHALLENGE
      DETAILS").
    The run exits normally. The check is polled constantly (over 32,000
    calls in one run).
  - Before this becomes a player setting:
    - completing a challenge, medals, per-car totals and save/reload need
      driving (a person, as in TU-6);
    - **Scoped (done).** The hook takes `lr`. The 64 call sites come
      down to seven callers seen in play:
      - `sub_827EBEE0` (the pause action, returning to 827EC3C0);
      - `sub_824D20A0` (824D20B8): the "1000 Club online" status, server
        and `sub_826F16B8`, which the home screen and the free-roam
        promotion read;
      - five general online callers: `sub_824A3650`, `sub_8253E628`,
        `sub_826BFC98`, `sub_8294EB28` and `sub_8294EBA0`.

      Bisection on `v4-club-begin`:
      - answering only the pause gate and the `sub_8294EBxx` pair brings
        back "server not available" inside the screen;
      - adding 824D20B8 restores the full flow;
      - answering just 827EC3C0 and 824D20B8 is enough.

      The probe now answers only those two by default. The other five keep
      the offline answer. `--pinyon_shift_server_probe_callers` takes
      `all` or a hex list for diagnosis, and a malformed list falls back to
      the default. `v4-club-begin` passes with the default: tutorial, car
      list, and "begin challenges" back to free roam.
    - **The promotion is 1000 Club itself.** With 824D20B8 answered, free
      roam shows the game's first-run "Visit the 1000 CLUB screen from the
      Pause Menu" hint in the prompt slot. `v4-race-start-wait` therefore
      cannot sign up for its race (it passes with the five general callers
      answered and 824D20B8 not). A LIVE player would have seen the same
      hint.
    - **After a visit** (`v4-club-then-race`: visit the screen, begin
      challenges, then the race route's sign-up inputs), the promotion is
      gone. The active-challenge prompt replaces it: "Enter the CURRENT CAR
      CHALLENGES screen…" with "PRESS … TO VIEW CAR CHALLENGE DETAILS". The
      Gauntlet sign-up banner still does not appear, and the route stays in
      free roam (mode 17). Whether the original online game also hid event
      sign-ups while car challenges were active, or whether the player must
      drive to the event marker, needs a person to judge in play before
      this becomes a player setting. (These wall-time club routes sometimes
      fail their first capture as blank during loading; the later captures
      are valid.)
  - **Goals saved offline (fixed 2026-10-07).** In play, completed goals
    showed "UPLOADING" forever and were gone after the next event. A
    completion goes to `CScoreboardManager::SubmitCarChallenge`
    (`sub_829490D8`), which calls the web service
    `Forza.WebServices.Challenge` / `ChallengeCompleted` (`sub_82B7A328`)
    and keeps the goal pending. Only the server's answer (`sub_82947DF8`,
    task type 8) commits it, through `sub_824D8300(challenge component,
    car, challenge)`. That sets the record's confirmed byte (+5) and moves
    the HUD state (+200) from 1 or 2 to 5. Without the answer the goal is
    unconfirmed and dropped. Answering every server check does not help,
    because the call is accepted and simply never answered.
    The fix is a default-off codegen hook at the entry of `sub_829490D8`
    (`PinyonShiftCarChallengeSubmitLocal`). With the probe on, it skips the
    web call and queues the (car, challenge) pair. About 120 frames later,
    a guest task calls `sub_824D8300`, which is when the server's answer
    used to arrive. A first version committed at submit time; the HUD was
    still in state 0 then, so the confirmation was ignored. The log shows
    `local_submit` followed by `local_commit` two seconds later, and the
    user confirmed the goals stay completed and survive a restart.
    - the garage-car cards render as noise in the eligible-car list. They
      look the same in CAR SELECT on both builds: this seed's profile holds
      `Thumbnail_N.xdc` files saved by builds before SDK `0bf0658` (BUGS.md,
      NP-0.6), so this is not a 1000 Club or v4 issue.
- [x] Verify that Rally and 1000 Club achievements unlock through the loaded
  DLC `spa.bin`, and handle unavailable online features without hangs. In
  the manual sessions, Rally's 206 and 208 (v4's XDBF) and 1000 Club's 216
  (0xD8, registered from its `spa.bin`) unlocked. Every session exited
  normally; the five general online callers keep their offline answer.

### TU-8: Canary DLC ports — S/M

Can start immediately; it helps both builds.

- [x] DLC `spa.bin` loading (SDK `63ae8f5`). Only IDs the title doesn't
  define are registered. The base XEX defines 50 achievements (155–205), v4
  defines 60 (155–215, Rally included). With 1000 Club enabled, v4 logs
  "Registered 10 achievement(s)" (216–225).
- [x] Headless `XamShowMarketplaceUI(Ex)` and
  `XamShowMarketplaceDownloadItemsUI` (SDK `63ae8f5`). They complete as an
  immediately closed system UI with overlapped completion, and never grant
  a licence. No FH1 route has called them yet.
- [x] Read-only Marketplace mounts (SDK `63ae8f5`). Native Rally entry and
  the stage start still pass with read-only DLC. The earlier shared
  Marketplace-root change is committed separately (SDK `2c10024`).
- [x] Optional: the symlink-in-use check and enumerator de-duplication.
  SDK `6ec6804` refuses content create and open when the root name would
  shadow an existing device link (`game:`, `update:`, …). The 21-package v4
  run is unchanged after it: 25 successful opens, `DLCRoot0`–`DLCRoot20`,
  no refusals, 10 DLC achievements. Exclude-common and de-duplication are
  not ported: every FH1 enumeration in all v4 and base runs passes flags
  0, and the 21-package enumeration returns exactly 21 distinct items
  (Marketplace content lives only under the common `0000000000000000`
  profile), so neither change would alter anything for this title.
- [x] A run with all 21 imported packages enabled
  (`v4-all-dlc-appdata-2026-09-27`, each enabled and payload-verified via
  `manage-fh1-dlc`). v4 mounts all 21 read-only as `DLCRoot0`–`DLCRoot20`
  and registers 1000 Club's 10 achievements; the other packages add none.
  It reaches free roam and shows a pause menu with both 1000 CLUB and
  HORIZON RALLY, with no crash. Car-pack gameplay remains DLC-4/5 work. The
  SDK has no host test harness for these; the receipts are real-content
  runs.

### TU-9: retire the base-disc Rally adapter — M

Depends on TU-6 passing and the default-build decision in TU-5.

- [ ] Remove the obsolete pieces listed in the review above, their render
  tests, environment flags and preparation recipes. Keep import, ownership
  and the launch gate.
- [x] Until then, if the adapter keeps shipping:
  - [x] Refuse to mount when the stage mapping is invalid: the built-in
    overlay now mounts only when `rally-stage.toml` parses and has stages,
    otherwise it records `dlc.rally.adapter_error`, so base festival races
    keep the stock flow.
  - [x] ~~Make a preparation failure disable only Rally.~~ **Decision
    (user, 2026-10-06): keep blocking.** A save with Rally parts needs the
    content, so a failed preparation still blocks launch on the base build.
    The v4 path skips this preparation entirely.
  - [x] After a successful swap, `prepare` deletes every
    `rally_adapter.previous-*` except the copy just retained (about 1 GB
    each); the 7 preparation tests pass.
  - [x] Tie the hub probe, the list probe and the private environment flags
    to render-test mode. The hub, list and ground probes already required
    it; `PINYON_SHIFT_RALLY_BUILTIN_PROBE`, `_PROGRESS`, `_TRACE`,
    `_PACE_PROBE` and `_AUDIO_PROBE` now go through `RallyPrivateFlag` /
    `RallyPrivateValue`, which ignore them outside render tests. Only the
    launcher's `PINYON_SHIFT_RALLY_PREPARED` stays player-facing. The base
    `fh1-rally-entry-assets` run emits the same nine `dlc.rally.*` events as
    before (it still fails only on its fixture's ledger expectation).

## Needs a decision or a person

Execution status, 2026-10-07:
- **Done:** TU-0, TU-1, TU-2, TU-3, TU-4, TU-5, TU-7 and TU-8. TU-6's
  acceptance run passed in the user's manual session. 1000 Club is
  playable offline through the launcher's opt-in "1000 Club offline"
  setting: goals are saved, achievements unlock, and events can still be
  entered.
- **Decided:** base stays the default with v4 as a launcher opt-in (TU-5,
  the user); a failed Rally preparation keeps blocking base launches (TU-9,
  the user); v4 ignores `rally-progress.toml` ledgers (TU-6).
- **Remaining:**
  - **TU-6 coverage.** The other championships, the 28 stages and the end
    sequence have not been played on v4. Nothing is known to fail.
  - **TU-7 player setting: built and confirmed, off by default.** The launcher's v4 row
    has a "1000 Club offline" checkbox (`manage-title-update.ps1
    club-on|club-off`, stored as `club` in
    `<state>/config/title-update.json`). `launch-preview.ps1
    -TitleUpdateV4` then adds the probe flags itself (verified: a plain
    launch logs "1000 Club runs offline" and installs the probe).
    `check-launcher.py` passes at 940 and 1080 wide. The race sign-up
    question is answered: with challenges active, the user can sign up for
    and enter events normally (2026-10-07). The scripted route failed only
    because its fixed inputs met the challenge prompt instead of the
    sign-up prompt.
  - **TU-9 retirement.** Deferred: the base adapter keeps shipping while
    base is the default build.

## Validation and completion rules

Follow DLC_BACKLOG's rules:
- Qualify on Vulkan.
- Use pinned private seeds through `tools/run-fh1-render-test.py`.
- Never write the AppData save, a pinned seed, the disc dump or the update
  package.
- Keep binaries, reconstructed images, traces and captures under ignored
  local paths.

For each completed item, record:
- the source and SDK revisions;
- the base, update and package hashes;
- which build ran (base or v4);
- the routes run and their results;
- known limitations.
