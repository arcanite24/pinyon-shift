# Achievements UI backlog: a screen worth opening

Created 2026-11-01 at `dev` `c2e70509`. Goal: turn the achievements screen
from a text list into one of the project's highlights, a screen players open
to see what to do next, and make unlocking feel like an event. Everything is
drawn by the host UI (NP-1.3) with the title's own fonts and textures read
from the player's disc, so it looks like part of Forza Horizon and ships no
game data.

Items are `AC-*`. This backlog takes over the achievements part of NP-5.3 in
[NATIVE_PORT_BACKLOG.md](NATIVE_PORT_BACKLOG.md).

## Where it stands

- **The screen is a settings list.** `src/ui/achievements_menu.cpp` builds a
  `hostui::MenuScreen`: one upper-case row per achievement with `50G` or
  `LOCKED`, the focused one's description as the note, and "N of M
  unlocked, X of Y gamerscore" as the body. Eight rows show at a time, so
  70 achievements are nine pages of scrolling. No icons, no categories, no
  dates, no progress. F7, SETTINGS > ACHIEVEMENTS and the title's
  `XamShowAchievementsUI` all open it.
- **The toast is plain.** `HostUi::DrawToasts`: a 520x96 gradient panel at
  the top of the safe area, magenta edge, the XDBF icon, "ACHIEVEMENT
  UNLOCKED", name and `NG`, 5 s with a 0.25 s fade. No motion, no sound.
- **The data is thin.** `rex::system::AchievementInfo` has id, label,
  description, unachieved description, image id, gamerscore and flags.
  `AchievementManager` adds `IsUnlocked` and `GetUnlockTime` (FILETIME,
  persisted in `user/achievements/<title>.toml`). 50 base achievements
  (155-205), 60 on v4 with Rally (to 215), 70 with 1000 Club (216-225)
  (`site/findings/content.toml`, "achievement ID ranges").
- **The SDK's ImGui overlay is unused.** Pinyon overrides
  `CreateAchievementsOverlay`; `rex::ui::AchievementsOverlayDialog` stays
  for other titles.
- **Pieces to reuse:**
  - `rex::ui::AchievementIconCache` loads the 64x64 XDBF icons (already
    used by the toast).
  - The host UI draws gradients, skewed textured rects and the game's
    vector fonts at any output size; it already loads
    `DirtMasks/SelectionContainer.xds` and the A/B button marks from
    `media/ui/textures/Horizon.zip` (`HostUi::LoadAssets`).
  - `Horizon.zip` holds textures that fit this screen (member names only;
    each is read from the player's disc at first open):

    | Use | Members |
    | --- | --- |
    | Completion tiers | `Wristbands/<Colour>{,Large,Xl}.xds`, `Wristbands/Platinum.xds` (the festival's own progression mark) |
    | Tile states | `Common/Tick.xds`, `Icons/MiniPanel/Locked.xds`, `Icons/Undiscovered Icon.xds`, `Icons/New_Icon.xds`, `Icons/MiniPanel/Star.xds`, `Icons/SkillStarSmall.xds` |
    | Rarity / reward stickers | `Icons/TicketStickerBronze/Silver/Gold.xds`, `Icons/MissionComplete.xds`, `Badges/Badge.xds` |
    | Tiles and panels | `Masks/IconTile.xds`, `Masks/IconTileLarge.xds`, `Masks/Hexagon.xds`, `DirtMasks/Panel01.xds`, `Common/CatagoryBar.xds`, `Icons/IconShadowLarge.xds` |
    | Bars | `DirtTextures/StatBarEmpty/Fill.xds`, `Kitparts/bars/*`, `Masks/Pill26pxSpecMask.xds` |
    | Shine and motion | `Specular/SPEC_sheen.xds`, `Kitparts/specular_shine/SPEC_sheen.xds`, `light_leak.xds` |
    | Button help | `Common/LBbutton.xds`, `Common/RBbutton.xds`, `Common/Xbutton.xds`, `Common/Ybutton.xds`, `Common/ScrollIndicator.xds` |

  - The save is self-describing (`site/findings/saves.toml`, "Profile
    values": named fields such as `Main/XP`, `Main/Credits`,
    `Main/TotalWinnings`), and the collectibles are mapped
    (`collectible_state.found` for discount signs and barn finds,
    `config/mod/fh1-symbols.toml`). That is the base for progress bars.
  - `HostUi::SetHudSource` draws persistent text over the game: the base
    for a tracked-achievement chip.

## Design

### The screen

One screen, 1280x720 title space, inside the 90 % safe area:

```text
+------------------------------------------------------------------------+
| ACHIEVEMENTS                       [wristband]  EARNED / TOTAL G   59 % |
| [=================================-------------------]  41 of 70       |
|                                                                        |
|  LB  ALL 41/70 | CAREER | EXPLORE | SKILLS | CARS | RALLY | 1000 CLUB RB |
|                                                                        |
|  CLOSEST TO UNLOCKING                           | [  big icon  ]       |
|  [icon 87/100] [icon 8/10] [icon 3/5]           | NAME                 |
|                                                 | 30G     UNLOCKED     |
|  [ic][ic][ic][ic][ic]                           | 12 OCT 2026          |
|  [ic][ic][ic][ic][ic]   <- grid, 5 x 3 visible   | description ...      |
|  [ic][ic][ic][ic][ic]                           | [====------] 37/100  |
|                                                 |                      |
| (A) DETAILS  (X) SORT: NEAREST  (Y) TRACK  (B) BACK                    |
+------------------------------------------------------------------------+
```

- **Header.** Gamerscore earned of total in the display face, percent, a
  bar with a slow sheen sweep, and the completion tier as a wristband
  (tiers follow the festival's own colour order, Platinum at 100 %; the
  order is checked in AC-0.3). Numbers count up over 0.4 s when the screen
  opens.
- **Tabs (LB/RB).** ALL, then categories, each with its own `n/m`. DLC tabs
  appear only when the package is installed. A finished category gets a
  tick on its tab.
- **Grid of tiles.** The 64x64 XDBF icon on the title's icon-tile mask,
  gamerscore on a pill. Unlocked: full colour, tick, a gold border on the
  highest-value ones. Locked: grey icon (a desaturated copy made at load,
  AC-1.4) with the lock mark, and a thin progress bar under the tile when
  progress is known. Secret (the XDBF does not show it before unlock):
  the undiscovered mark and "SECRET". Newly unlocked since the screen was
  last opened: the NEW sticker until it is focused once.
- **Focus.** The focused tile lifts (scale 1.08, 120 ms ease-out), gets the
  magenta selection mask and one sheen pass. The side panel follows it.
- **Detail panel.** Large icon, name, gamerscore, state and date unlocked
  (player's locale), the description (the "how to" text while locked),
  and the progress bar with numbers when known (AC-4). Never an invented
  number: no source, no bar.
- **Closest to unlocking.** On ALL, a row of up to three locked
  achievements with the highest known progress fraction. This is the main
  nudge: it tells the player what is nearly done.
- **Sort (X).** Default (the title's order), nearest to done, locked
  first, recently unlocked, gamerscore.
- **Track (Y).** Pins one locked achievement; while playing, a small chip
  (icon, name, `37/100`) sits in a corner of the safe area and updates
  when its counter changes. Off when nothing is tracked; a setting hides
  it.
- **Input.** D-pad and stick move in the grid, LB/RB or Q/E switch tabs,
  mouse hover focuses and the wheel scrolls, touch taps a tile and swipes
  tabs (Android). The title's own `XamShowAchievementsUI` opens the same
  screen.

### The unlock moment

- **Toast.** Slides down from the top of the safe area (180 ms), the icon
  pops in with a short overshoot, the gamerscore counts up, a sheen passes
  over the panel, then it slides away. The total gamerscore and the
  wristband tier show on its second line ("740 G total"). Higher-value
  achievements (50 G and up, and the last one of a category) get the large
  variant with the light leak.
- **Sound.** The title's own UI notification cue if the FMOD event can be
  played from the host without guest state (AC-3.3); otherwise none. No
  shipped audio.
- **Milestones.** Optional toasts at 25/50/75 % of a counted achievement
  ("DISCOUNT SIGNS 50 / 100"), off by default, at most one per minute.
- **Completion.** Finishing a category shows a banner toast with its
  wristband; 100 % shows the Platinum wristband once.

### Data: our own catalogue

`AchievementInfo` stays as the SDK has it. Pinyon adds
`config/achievements/fh1.toml`, keyed by achievement ID only, with our own
classification and no game strings:

```toml
[[achievement]]
id = 172
category = "explore"
progress = "collectibles.discount_signs"   # a source AC-4 implements
```

Names and descriptions still come from the XDBF (and the DLC `spa.bin`), so
the screen is in every language the title is. Category and UI labels go in
`src/achievements/achievement_strings.cpp` (done: see AC-2.7 under
Progress).

### Host UI work

`MenuScreen` is row-based. Rather than force a grid into it, the host UI
gets a second screen kind: a screen with a `Paint(Painter&, Clock)`
callback and its own hit rectangles, where `Painter` exposes the drawing
`HostUi` already has (rects, gradients, textures, text, wrapped text) in
title pixels. Navigation gains `kPrevTab`, `kNextTab`, `kAuxX` and
`kAuxY`. The settings menu stays on `MenuScreen`.

## Risks and open questions

- **Reading progress safely.** The host UI runs on the UI thread; the guest
  owns the profile. Progress must come from a snapshot taken at a safe
  point (a guest-side hook already used for the collectibles, or the
  profile save path), read-only, never from live guest pointers during
  drawing.
- **Which achievements can show progress.** Unknown until AC-0.2. Binary
  ones (win a specific event) have none and must look fine without a bar.
- **CJK.** The title's Latin fonts are meshes; Chinese, Japanese and Korean
  achievement names need bitmap fonts. Resolved in AC-2.7: the host UI
  falls back to the title's own `JPB`, `KORB` and `CHTB` bitmap fonts.
- **Small screens.** Five 96 px tiles a row must stay readable on the Deck
  (7") and the Odin; AC-5.2 checks it.
- **Gamerscore pressure.** No online rarity exists; stickers mark value,
  not rarity, and the copy says so.

## Verification rules

- Every screen state has a capture in the `fh1-host-features` route (or a
  new `fh1-achievements` route) from a pinned seed made with
  `tools/create-render-seed.py`; the seed's
  `user/achievements/<title>.toml` sets which are unlocked. Seeds for 0 %,
  partial and 100 %, base and v4 with both DLC.
- Progress numbers are checked against the game's own menus (signs found
  on the map, garage count) on the reference save, read-only.
- No frame-time cost while playing: the toast and track chip draw only
  while visible; one Odin in-run A/B with the chip on and off.
- Devices: multivac (4K and ultrawide), Steam Deck, Odin (touch), Mac.

## Items

### AC-0 Survey (no player-visible change)

| ID | Item | Size |
| --- | --- | --- |
| AC-0.1 | Classify all 70 achievements into categories and record secret flags (XDBF flags bit `0x8`, show-unachieved, to confirm) in `config/achievements/fh1.toml` | S |
| AC-0.2 | For each, name a progress source or "none": profile value-tree fields, collectibles found, garage count, event results. Record each source in `site/findings` with confidence | M |
| AC-0.3 | Decode the wristband, sticker, tile and bar textures once into `.local/ui-catalogue` and pick the set; check the wristband colour order against the game's own progression | S |
| AC-0.4 | Find the title's UI notification sound event and whether the host can trigger it | S |

### AC-1 Host UI foundation

| ID | Item | Size |
| --- | --- | --- |
| AC-1.1 | Painted screen kind (`Paint` callback, `Painter`, hit rectangles, scroll), with the menu's backdrop, safe area and button help shared | M |
| AC-1.2 | Tab and auxiliary navigation commands on pad (LB/RB, X/Y), keyboard (Q/E, R/T), mouse wheel and touch swipe | S |
| AC-1.3 | Lazy texture set from `Horizon.zip` for the screen, released when the host UI closes | S |
| AC-1.4 | Grey copies of locked icons: `AchievementIconCache` keeps the decoded RGBA so a desaturated texture can be made once (ShiftGlue change) | S |
| AC-1.5 | Animation helpers: per-screen clock, ease-out, count-up, sheen pass; paint requests only while something moves | S |

### AC-2 The screen

| ID | Item | Size |
| --- | --- | --- |
| AC-2.1 | Header: gamerscore, percent, sheen bar, wristband tier, count-up | S |
| AC-2.2 | Category tabs with counts, DLC tabs by installed package, tick on finished | S |
| AC-2.3 | Tile grid: icon, pill, unlocked/locked/secret/NEW states, focus lift | M |
| AC-2.4 | Detail panel: big icon, state, unlock date in the player's locale, description, progress | S |
| AC-2.5 | Sort modes, kept for the session | S |
| AC-2.6 | Mouse and touch: hover focus, click to open, wheel scroll, tap and swipe | S |
| AC-2.7 | Strings for the 18 languages; CJK fallback | S |

### AC-3 The unlock moment

| ID | Item | Size |
| --- | --- | --- |
| AC-3.1 | Animated toast (slide, icon pop, count-up, sheen), large variant for 50 G and category finishers | M |
| AC-3.2 | Category and 100 % completion banners | S |
| AC-3.3 | Notification sound if AC-0.4 found a safe path | S |
| AC-3.4 | Milestone toasts at 25/50/75 %, off by default, rate-limited | S |

### AC-4 Progress

| ID | Item | Size |
| --- | --- | --- |
| AC-4.1 | Progress snapshot at a safe guest point, read-only, refreshed on profile save and collectible events | M |
| AC-4.2 | Progress bars on tiles and the detail panel, sources from AC-0.2 only | S |
| AC-4.3 | Closest-to-unlocking row | S |
| AC-4.4 | Track one achievement: HUD chip through `SetHudSource`, persisted with the host settings | S |

### AC-5 Settings, platforms, qualification

| ID | Item | Size |
| --- | --- | --- |
| AC-5.1 | Settings: toast position, milestone toasts, track chip, show secret descriptions | S |
| AC-5.2 | Legibility pass on the Deck and Odin; tile size per output height | S |
| AC-5.3 | Route captures for every state; Odin in-run A/B of the chip | S |
| AC-5.4 | Docs site: `playing.md` controls, `features.toml`, the findings from AC-0 | S |

## Rejected or set aside

| Idea | Why |
| --- | --- |
| Keep the SDK's ImGui overlay and restyle it | ImGui does not use the title's fonts and textures; the host UI already does |
| Online rarity percentages | No service; a made-up number would mislead |
| Steam achievements | Not shipped through Steam; revisit only if that changes |
| Shipping our own icon art | The disc has what the screen needs; nothing to license or distribute |

## Order and estimate

AC-0 first (2-3 days): it decides how much of AC-4 exists. Then AC-1 and
AC-2 together (about a week) give the new screen without progress; AC-3
(2-3 days) the unlock moment; AC-4 (3-5 days, mostly reverse engineering)
the bars and tracking; AC-5 (2 days) finishes it. About three weeks in all.

## Progress

AC-0 to AC-4 done on 2026-11-01 (branch `feat/achievements-ui`), checked
on Windows with the base build only. Route:
`config/render-tests/fh1-achievements-ui.fh1test` (unlock toast, screen,
tabs, sort, track and untrack, the chip in free roam); host UI is not in
captures, so the screen was checked from desktop grabs and the
`achievements.*` and `hostui.*` events.

| Item | State |
| --- | --- |
| AC-0.1 | Done. The catalogue is a C++ table (`src/achievements/fh1_achievements.cpp`), not `config/achievements/fh1.toml`: it holds only IDs and our classification, and nothing else reads it. No achievement is secret (every XDBF entry has the show-unachieved flag) |
| AC-0.2 | Done. Sources: wristbands (`Main/WristbandLevel` + 1), discount signs (the live collectible census, else `Main/UpgradeDiscount`), Festival Racers beaten (`Main/NumRaceEncountersWon`, probable). Popularity rank, roads and speed traps have no profile field (recorded as a negative result) |
| AC-0.3 | Done. Wristband XL art and order, ticket stickers, controller glyphs; 1000 Club icons come from its `spa.bin` |
| AC-0.4 | Done. The title's own achievement sound is silent (`MiniAchieve` maps to `Blank`); the unlock plays the HUD reward cue through the audio manager inside `CAudioEngine::Update` |
| AC-1 | Done: painted screens (`hostui/painter.h`), LB/RB, X/Y, Q/E/Tab, R/T, wheel, click on release and swipe, `Horizon.zip` textures released with the host UI, grey icons in `ui/achievement_icons.cpp` (host side, no ShiftGlue change) |
| AC-2 | Done |
| AC-2.7 | Done. The screen's and toasts' labels are in `src/achievements/achievement_strings.cpp` for the 14 languages that have achievement strings (EN, JA, DE, FR, ES, IT, KO, ZH-Hant, PT, PL, RU, SV, NB, NL), chosen by `user_language` like the XDBF names; Danish, Finnish, Czech and Hungarian run the title with language 1 and get English, as the title's own achievement names do. Characters the vector fonts lack come from the title's bitmap fonts (`hostui/bitmap_font.cpp`, format on the UI findings page), the order set by the language; long CJK words break between characters. Checked in Japanese, Korean and Russian (screen, chip, toasts); Chinese only by coverage check |
| AC-3 | Done. Milestones are off by default (`pinyon_shift_achievement_milestones`); the tracked achievement always notifies |
| AC-4 | Done. Progress refreshes at each profile load and save and every two seconds while the screen or a tracked achievement needs it; the chip hides on the pause map and other 16:9 screens |

Not yet checked: the v4 build (Rally and 1000 Club tabs and icons), the
reference save, the sound by audio capture, controllers, the Deck,
Android and the Mac. These belong to AC-5.
