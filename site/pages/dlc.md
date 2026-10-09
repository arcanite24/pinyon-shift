---
title: DLC and title update
section: Playing
order: 3
description: Import your own Forza Horizon DLC packages and build the optional title update v4 version.
---

# DLC and title update

DLC comes from your own Xbox 360 packages. The launcher verifies each one against a pinned catalog of 21 *Forza Horizon* packages, then imports it. Imports start disabled, and each package is enabled separately. Close the game before changing DLC.

## Supported packages

| Package | State |
| --- | --- |
| Monthly car packs (October to April) | Qualified: cars appear in the Autoshow, can be bought and driven |
| VIP Membership, Honda Challenge, Pre-Order, Season Pass and single cars | Cars qualified. The Honda challenge flow isn't qualified |
| Horizon Rally | Native on the v4 build. On the base build, a prepared overlay makes the championships playable from <kbd>F6</kbd> |
| 1000 Club | Offline car challenges with saved medals on the v4 build ("1000 Club offline" in the launcher) |
| Treasure Map | Included and on by default |

Import every copy of a package you own: verified variants of the same package combine their licences. The full November pack, for example, needs its full-licence copy.

## Title update v4

The base disc build is the default. The optional v4 build applies title update v4 to the USA disc and runs the original Rally and 1000 Club code. It's built from your disc and your own copy of the update, which is verified page by page before it's installed.

- Windows: `tools/build-v4.ps1` from a repository checkout.
- Android: `python tools/pinyon.py android build --title-update-v4`.

> A save written by the v4 build can't be loaded by the base build afterwards. The launcher backs up the save before the first v4 start.

The v4 build is still under qualification. Details are in the [title update v4 backlog](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/TITLE_UPDATE_V4_BACKLOG.md) and the [DLC backlog](https://github.com/arcanite24/pinyon-shift/blob/dev/docs/DLC_BACKLOG.md).
