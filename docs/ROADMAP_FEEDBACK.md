# Pinyon Shift community requests and roadmap priorities

Review date: **2026-10-04**. Linux and Steam Deck, usable Android support,
and DLC are the strongest recurring feature themes in the comments reviewed.
Setup failures and unstable gameplay are the larger immediate barriers to
playing. The recommendation is to keep the current Linux, FH1 v4 title-update,
DLC and Android setup work, with stability and installation fixes taking
priority before expanding the platform list further.

## Scope and counting

This review covers visible comments on the relevant FH1 posts linked from
[arcanite24's Reddit submissions](https://www.reddit.com/user/arcanite24/submitted/),
the supplied [X announcement and replies](https://x.com/nerijs/status/2106440715295486355),
and all **62 GitHub issues**, including their available comments, returned by
the repository issue listing at the time of review. Pull requests are excluded.
The linked [playable preview discussion](https://www.reddit.com/r/decomps/comments/1vzmffl/pinyon_shift_playable_preview_of_forza_horizon/)
provides supplemental context; it was posted by another user.

The order below is a qualitative assessment of repeated requests and expressed
interest, not a vote count or a complete census of hidden replies. Maintainer
replies and duplicate comments do not constitute additional demand. Issue
counts describe reports, not distinct root causes, and closed reports can
describe work already shipped.

## Most requested features

| Order | Request | Observed demand and evidence | Recommended placement |
| --- | --- | --- | --- |
| 1 | Linux and Steam Deck | Repeated in the [0.4 Reddit comments](https://www.reddit.com/r/recomps/comments/1wwt8dz/pinyon_shift_v040_is_out_lots_of_performance/), the [Linux X reply](https://x.com/andrezeirauno/status/2106538652742439269), the [preview discussion](https://www.reddit.com/r/decomps/comments/1vzmffl/pinyon_shift_playable_preview_of_forza_horizon/) and [issue 310's comments](https://github.com/arcanite24/pinyon-shift/issues/310). | Linux in progress; Steam Deck qualification next. |
| 2 | Easier Android installation and better performance | Reddit users ask for an APK and where to put files. [An X follow-up](https://x.com/rerangedmork/status/2106487435882565842) asks how to install; [another tester](https://x.com/Denissboss11/status/2106516566179193204) reports heat and stutter after a few minutes. | Build, install and data transfer in progress; sustained performance next; lower-end devices mid term. |
| 3 | DLC, including Horizon Rally | Two separate X users ask about [DLC priority](https://x.com/0x34ffffff/status/2106467574741438839) and [Horizon Rally](https://x.com/Jlee20211Lee/status/2106596925164105986). A [Reddit commenter](https://www.reddit.com/r/decomps/comments/1v122rk/forza_horizon_1_recomp_in_the_works/) also specifically requests the expansion. | In progress; list car packs and Horizon Rally explicitly and validate each supported package. |
| 4 | Nintendo Switch | Requested on [Reddit](https://www.reddit.com/r/decomps/comments/1wwt8vg/pinyon_shift_v040_is_out_lots_of_performance/) and [X](https://x.com/AkBuldur/status/2106513020885098737). | Mid term, beginning with a feasibility and performance check on hardware. |
| 5 | Racing wheels and force feedback | [Issue 337](https://github.com/arcanite24/pinyon-shift/issues/337) asks for wheels; the [0.4 Reddit thread](https://www.reddit.com/r/recomps/comments/1wwt8dz/pinyon_shift_v040_is_out_lots_of_performance/) independently asks for force feedback. | Mid term; include pedals, calibration and force feedback in the scope. |
| 6 | macOS | Explicit request in [issue 310](https://github.com/arcanite24/pinyon-shift/issues/310). The maintainer's reply already puts Linux and Steam Deck first. | Mid term, after the Linux path is qualified. |
| 7 | Compatibility with existing FH1 mods | The [0.4 Reddit discussion](https://www.reddit.com/r/recomps/comments/1wwt8dz/pinyon_shift_v040_is_out_lots_of_performance/) mentions the XE mod and hopes existing modded content will work. | Mid term; evaluate existing mods through the supported override workflow. |
| 8 | Custom music and radio stations | A user asks for music replacement in the [0.3 Reddit thread](https://www.reddit.com/r/recomps/comments/1wurxp0/pinyon_shift_030_the_xbox_360_forza_horizon/); the maintainer replies that custom radio is planned. | Mid term; add the previously announced feature to the public list. |
| 9 | Save migration | [Issue 335](https://github.com/arcanite24/pinyon-shift/issues/335) reports a crash after copying a Xenia save. This is a compatibility report, rather than an explicit importer request. | Recommended next: validate an imported copy and preserve the existing profile. |
| 10 | Multiplayer restoration | One visible request in the [preview discussion](https://www.reddit.com/r/decomps/comments/1vzmffl/pinyon_shift_playable_preview_of_forza_horizon/). | Research only; assess LAN feasibility before promising online services. |

Requests for Motorsport and FH2 also recur in the
[0.3 thread](https://www.reddit.com/r/recomps/comments/1wurxp0/pinyon_shift_030_the_xbox_360_forza_horizon/)
and the older discussions. They express interest in separate recompilations,
not features required to finish FH1. Keep them outside FH1's delivery queue.

## The largest immediate barriers

The issue snapshot contains **33 open and 29 closed issues**. Of the open
issues, **20 have crash-report titles** and **7 concern setup or compilation**.
Across all releases, at least **30 issues from 23 distinct GitHub authors**
report setup or build failures. The latter are historical reports, not 30
currently outstanding failures. Examples still open at review time include
[350](https://github.com/arcanite24/pinyon-shift/issues/350),
[347](https://github.com/arcanite24/pinyon-shift/issues/347) and
[346](https://github.com/arcanite24/pinyon-shift/issues/346).

Crash reports should be grouped by failure and release before assigning
engineering effort. For example,
[321](https://github.com/arcanite24/pinyon-shift/issues/321),
[326](https://github.com/arcanite24/pinyon-shift/issues/326) and
[331](https://github.com/arcanite24/pinyon-shift/issues/331) describe the same
AMD Vulkan failure, with a fix shipped but hardware confirmation still needed;
[336](https://github.com/arcanite24/pinyon-shift/issues/336) is identified as a
duplicate. Other reports describe crashes during the
[intro transition](https://github.com/arcanite24/pinyon-shift/issues/343), the
[first showcase](https://github.com/arcanite24/pinyon-shift/issues/333), or
[relaunch after changing the graphics API](https://github.com/arcanite24/pinyon-shift/issues/345).

Recurring stutter and corrupted cinematics remain visible in the
[0.4 comments](https://www.reddit.com/r/recomps/comments/1wwt8dz/pinyon_shift_v040_is_out_lots_of_performance/).
[Issue 328](https://github.com/arcanite24/pinyon-shift/issues/328) was closed
with a shader-compilation fix, but subsequent reports still warrant checking
on the current release. Treat improved performance and complete correctness
as separate acceptance criteria.

The recommendation is to prioritise a reliable intro, first race, first
showcase, save/relaunch and free-roam session, plus a clean installation on a
fresh machine. Peak 4K or 120 fps results should follow broad playability.

## Suggested additions to the roadmap

1. **A tested hardware table and useful preflight checks.** Publish the release,
   GPU or Android SoC, driver, resolution, settings and sustained performance.
   Check required graphics capabilities before the long build. Players asking
   about older GPUs in the [X replies](https://x.com/JunkieXS_/status/2106623967830437999)
   need a clear supported configuration, not a promise based on another game's
   performance.
2. **Android sessions measured after the device warms up.** Recommend a
   sustainable 720p/30 fps baseline on qualified devices, then higher targets
   where measurements support them. Record frame-time spikes and thermal
   behaviour over 20-30 minutes. This is a proposed acceptance target, not a
   claim of current support; the [Android documentation](ANDROID.md) already
   records thermal throttling on the reference device.
3. **Finish Android deployment in the launcher.** Extend the existing APK build
   with device detection, USB installation, data-copy progress and actionable
   errors. The [current process](ANDROID.md) still requires manual installation
   and data transfer. Build each player's package locally from their disc.
4. **Safe save import and transfer.** Support validated copies from Xenia and
   Xbox 360 where compatible, back up the destination, and explain unsupported
   formats or DLC dependencies before changing it. Start with explicit export
   and import; cloud synchronisation can wait for demonstrated demand.
5. **Steam Deck as a qualification milestone.** Include Steam Input, readable
   menus, suspend/resume and sustainable presets. Completing a Linux build is
   a prerequisite, not proof that the handheld experience is ready.
6. **Release update and repair without rebuilding everything unnecessarily.**
   Keep the existing launcher-update goal, prioritise save preservation and
   resumable setup, and measure build reuse before promising faster updates.

Wheel support and custom radio should also be explicit public items because
they have direct requests. Existing-mod compatibility deserves a documented
route; evaluating XE content does not imply accepting an unverified modified
disc as the base installation.

## Changes to the public roadmap

The [README roadmap](../README.md#roadmap) now groups priorities into in
progress, next, mid term and research. Current Linux, v4 title-update, DLC and
Android setup work stays in progress. Mid term includes lower-end Android,
Switch, macOS, wheels, mod management and custom radio. Multiplayer and
cross-title content remain research; other Forza recompilations are separate
projects.

The review also removes stale open items: the initial Android build and crowd
and purchase animation fixes already shipped in [0.4.0](releases/0.4.0.md).
Android is still a developer alpha. FH1 v4 title-update and DLC support remain
in progress; verifying a package alone does not establish gameplay support.
